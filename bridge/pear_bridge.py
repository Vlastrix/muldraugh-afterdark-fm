"""Local SP companion for Muldraugh Afterdark FM. Python 3.9+, standard library only."""
import argparse
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote
from urllib.request import ProxyHandler, Request, build_opener

LOG = logging.getLogger("pear-radio")
STALE_SECONDS = 3.0
CONTROL_FILE = "PearCarRadio.control.txt"
STATUS_FILE = "PearCarRadio.status.txt"


def disable_console_selection(kernel32=None):
    """Windows QuickEdit can freeze this process when text is selected by mouse.

    Set only this console's input mode, without changing registry preferences.
    A redirected console / other OS needs no adjustment.
    """
    if kernel32 is None:
        if os.name != "nt":
            return False
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetConsoleMode.restype = wintypes.BOOL
        kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetConsoleMode.restype = wintypes.BOOL
    import ctypes
    from ctypes import wintypes
    mode = wintypes.DWORD()
    handle = kernel32.GetStdHandle(-10 & 0xffffffff)  # STD_INPUT_HANDLE
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    # Keep Ctrl+C (ENABLE_PROCESSED_INPUT) and all unrelated input flags.
    new_mode = (mode.value | 0x0080) & ~0x0040  # EXTENDED_FLAGS / QUICK_EDIT_MODE
    return bool(kernel32.SetConsoleMode(handle, new_mode))


class PearError(Exception):
    pass


class BridgeLock:
    """An OS lock is released even if the companion crashes."""
    def __init__(self, path):
        self.file = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0, os.SEEK_END)
                if self.file.tell() == 0:
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise

    def close(self):
        self.file.close()


class PearAPI:
    def __init__(self, port=26538):
        self.base = "http://127.0.0.1:{}".format(port)
        self.token = None
        self.opener = build_opener(ProxyHandler({}))

    def request(self, method, path, data=None, timeout=1.5):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        payload = json.dumps(data).encode("utf-8") if data is not None else None
        request = Request(self.base + path, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                body = response.read(1024 * 1024)
                return json.loads(body.decode("utf-8")) if body else None
        except HTTPError as error:
            if error.code == 401:
                self.token = None
            raise PearError("Pear HTTP {}: {}".format(error.code, path)) from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise PearError("No valid response from Pear: {}".format(error)) from error

    def connect(self):
        # This is the only request allowed to wait for Pear's authorization dialog.
        LOG.info("Connecting to Pear. If prompted, authorize PZPearCarRadio.")
        auth = self.request("POST", "/auth/PZPearCarRadio", timeout=60)
        if not isinstance(auth, dict) or not auth.get("accessToken"):
            raise PearError("Pear did not return an access token")
        self.token = auth["accessToken"]

    def get(self, endpoint):
        result = self.request("GET", "/api/v1/" + endpoint)
        if result is not None and not isinstance(result, dict):
            raise PearError("Pear returned an unexpected state: " + endpoint)
        return result

    def post(self, endpoint, data=None):
        return self.request("POST", "/api/v1/" + endpoint, data)


def read_control(path, now=None):
    """Reject partial, malformed and stale snapshots rather than replaying commands."""
    now = time.time() if now is None else now
    try:
        before = path.stat()
        if not -1 <= now - before.st_mtime <= STALE_SECONDS or before.st_size > 4096:
            return None
        text = path.read_text(encoding="utf-8")
        after = path.stat()
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            return None
        values = {}
        for line in text.splitlines():
            key, value = line.split("=", 1)
            if key in values:
                return None
            values[key] = unquote(value)
        frame = int(values["frame"])
        volume = float(values["volume"])
        action_id = int(values["action_id"])
        if (values["protocol"] != "1" or values["commit"] != str(frame)
                or frame < 1 or action_id < 0
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", values["session"])
                or values["active"] not in ("0", "1")
                or values["playing"] not in ("0", "1")
                or values["action"] not in ("none", "next", "previous")
                or not math.isfinite(volume) or not 0 <= volume <= 100):
            return None
        return dict(session=values["session"], frame=frame,
                    active=values["active"] == "1", playing=values["playing"] == "1",
                    volume=round(volume), vehicle=values["vehicle"],
                    action_id=action_id, action=values["action"], source_mtime=after.st_mtime)
    except (OSError, UnicodeError, ValueError, KeyError):
        return None


class ControlReader:
    def __init__(self, path):
        self.path = path
        self.last_good = None

    def read(self, now=None):
        now = time.time() if now is None else now
        current = read_control(self.path, now)
        if current is not None:
            self.last_good = current
        # A read can overlap Lua's short write. Keep the previous COMPLETE state
        # only until its original mtime expires, never extending the watchdog.
        if self.last_good and -1 <= now - self.last_good["source_mtime"] <= STALE_SECONDS:
            return self.last_good
        return None


def write_status(path, values):
    body = dict(protocol="1", timestamp=str(time.time()), **values)
    content = "".join("{}={}\n".format(key, quote(str(value), safe=""))
                      for key, value in body.items())
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(str(temporary), str(path))


class RadioController:
    def __init__(self, api):
        self.api = api
        self.owned = False
        self.saved_volume = None
        self.desired = None
        self.volume = None
        self.last_action = None
        self.song = {}
        self.last_poll = -100.0
        self.session = ""

    def release(self):
        if self.owned:
            # Preserve ownership on failure so the next attempt retries the pause.
            self.api.post("pause")
            if self.saved_volume is not None:
                self.api.post("volume", {"volume": self.saved_volume})
            self.owned = False
            self.saved_volume = None
        self.desired = None
        self.volume = None
        self.song = {}

    def step(self, state, now):
        if not state or not state["active"]:
            self.release()
            if state:
                self.session = state["session"]
                self.last_action = (state["session"], state["action_id"])
            return self.status("Ready. Tune the car radio to Afterdark FM.")

        if state["session"] != self.session:
            self.release()
            self.session = state["session"]
            # Never replay a button from a previous game or bridge restart.
            self.last_action = (state["session"], state["action_id"])

        desired = (state["vehicle"], state["playing"])
        if state["playing"]:
            if not self.owned:
                current = self.api.get("volume") or {}
                value = current.get("state")
                self.saved_volume = value if isinstance(value, (int, float)) else None
                self.owned = True
            if self.volume != state["volume"]:
                self.api.post("volume", {"volume": state["volume"]})
                self.volume = state["volume"]
            if self.desired != desired:
                self.api.post("play")
        elif self.owned and self.desired != desired:
            self.api.post("pause")
        self.desired = desired

        action_key = (state["session"], state["action_id"])
        if action_key != self.last_action:
            # Consume before sending: never repeat Next on a lost HTTP response.
            self.last_action = action_key
            if state["playing"] and state["action"] != "none":
                self.api.post(state["action"])
                self.last_poll = -100.0

        if now - self.last_poll >= 1:
            self.song = self.api.get("song") or {}
            self.last_poll = now
        if not self.song.get("videoId"):
            message = "Open and play a song or playlist in Pear."
        elif not state["playing"]:
            message = "Paused: check the car radio power and controls."
        elif self.song.get("isPaused") is not False:
            message = "Pear is paused or loading. Press Pause, then Resume."
        else:
            message = "Playing from Pear."
        return self.status(message, state["playing"])

    def status(self, message, desired_playing=False):
        return dict(session=self.session, connected="1", message=message,
                    playing="1" if desired_playing and self.song.get("videoId")
                    and self.song.get("isPaused") is False else "0",
                    title=str(self.song.get("title", ""))[:240],
                    artist=str(self.song.get("artist", ""))[:160])


def run_bridge(zomboid_dir, port=26538, stop_event=None, on_status=None, api_factory=PearAPI):
    """Run the controller on a worker thread or in the developer console."""
    stop_event = stop_event or threading.Event()
    folder = Path(zomboid_dir) / "Lua"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        instance_lock = BridgeLock(folder / "PearCarRadio.lock")
    except OSError:
        LOG.error("Another bridge is running or its lock file is unavailable. Close the other bridge.")
        return 1
    api = api_factory(port)
    controller = RadioController(api)
    controls = ControlReader(folder / CONTROL_FILE)
    LOG.info("Singleplayer bridge. Files: %s", folder)
    LOG.info("Open Pear, enable API Server and select a song or playlist.")
    last_error = None
    next_connect = 0.0
    last_message = None
    try:
        while not stop_event.is_set():
            now = time.monotonic()
            try:
                if not api.token:
                    if now < next_connect:
                        stop_event.wait(0.25)
                        continue
                    next_connect = now + 5
                    api.connect()
                    if stop_event.is_set():
                        break
                    # A reconnect must reapply the desired state.
                    controller.desired = None
                    controller.volume = None
                    controller.last_poll = -100.0
                state = controls.read()
                status = controller.step(state, time.monotonic())
                if state is None:
                    status["message"] = "No recent mod signal. Restart Zomboid and tune to Afterdark FM."
                last_error = None
            except PearError as error:
                status = dict(connected="0", playing="0", session=controller.session,
                              message="Pear is offline. Check API Server.", title="", artist="")
                if on_status:
                    on_status(status.copy())
                if str(error) != last_error:
                    LOG.warning("%s", error)
                    last_error = str(error)
                # Connection failures also need backoff, even with an existing token.
                try:
                    write_status(folder / STATUS_FILE, status)
                except OSError as file_error:
                    LOG.warning("Could not write status: %s", file_error)
                stop_event.wait(2)
                continue
            if on_status:
                on_status(status.copy())
            try:
                write_status(folder / STATUS_FILE, status)
            except OSError as error:
                LOG.warning("Could not write status: %s", error)
            if status["message"] != last_message:
                LOG.info("%s", status["message"])
                last_message = status["message"]
            stop_event.wait(0.25)
    except KeyboardInterrupt:
        LOG.info("Stopping bridge...")
    finally:
        try:
            controller.release()
        except PearError as error:
            LOG.warning("Could not pause Pear on shutdown: %s", error)
        try:
            write_status(folder / STATUS_FILE, dict(
                connected="0", playing="0", session=controller.session,
                message="Bridge stopped.", title="", artist=""))
        except OSError:
            pass
        instance_lock.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zomboid-dir", type=Path, default=Path.home() / "Zomboid")
    parser.add_argument("--port", type=int, default=26538)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if disable_console_selection():
        LOG.info("Mouse selection disabled to prevent the console from suspending the bridge.")
    return run_bridge(args.zomboid_dir, args.port)


if __name__ == "__main__":
    raise SystemExit(main())

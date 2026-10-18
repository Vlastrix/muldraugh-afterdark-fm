import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

SPEC = importlib.util.spec_from_file_location(
    "pear_bridge", Path(__file__).resolve().parents[1] / "bridge" / "pear_bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def snapshot(**changes):
    state = dict(session="test-session", frame=1, active=True, playing=True,
                 volume=42, vehicle="12", action_id=0, action="none")
    state.update(changes)
    return state


class FakePear:
    def __init__(self):
        self.calls = []
        self.song = dict(videoId="abcdef12345", title="Cancion", artist="Artista", isPaused=False)
        self.fail_pause = False

    def get(self, endpoint):
        self.calls.append(("get", endpoint, None))
        return {"state": 73} if endpoint == "volume" else self.song.copy()

    def post(self, endpoint, data=None):
        self.calls.append(("post", endpoint, data))
        if endpoint == "pause" and self.fail_pause:
            raise bridge.PearError("offline")
        if endpoint == "pause":
            self.song["isPaused"] = True
        elif endpoint == "play":
            self.song["isPaused"] = False


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "control"

    def write(self, **changes):
        values = dict(protocol="1", session="test-session", frame="5", active="1",
                      playing="1", volume="42", vehicle="12", action_id="0",
                      action="none", commit="5")
        values.update(changes)
        self.path.write_text("".join("{}={}\n".format(k, v) for k, v in values.items()), encoding="utf-8")

    def test_complete_fresh_snapshot(self):
        self.write()
        self.assertEqual(bridge.read_control(self.path)["volume"], 42)

    def test_partial_and_invalid_snapshots_are_ignored(self):
        for changes in (dict(commit="4"), dict(volume="nan"), dict(volume="101"),
                        dict(active="yes"), dict(session="../escape"), dict(action="delete")):
            with self.subTest(changes=changes):
                self.write(**changes)
                self.assertIsNone(bridge.read_control(self.path))
        self.path.write_text("protocol=1\nframe=5\n", encoding="utf-8")
        self.assertIsNone(bridge.read_control(self.path))

    def test_stale_snapshot_never_starts_music(self):
        self.write()
        old = time.time() - 10
        os.utime(str(self.path), (old, old))
        self.assertIsNone(bridge.read_control(self.path))
        pear = FakePear()
        bridge.RadioController(pear).step(bridge.read_control(self.path), 0)
        self.assertEqual(pear.calls, [])

    def test_duplicate_keys_are_rejected(self):
        self.write()
        with self.path.open("a") as output:
            output.write("playing=0\n")
        self.assertIsNone(bridge.read_control(self.path))

    def test_partial_write_does_not_pause_but_watchdog_still_expires(self):
        self.write()
        written = self.path.stat().st_mtime
        reader = bridge.ControlReader(self.path)
        self.assertTrue(reader.read(written)["playing"])
        self.path.write_text("protocol=1\nframe=6\n", encoding="utf-8")
        self.assertTrue(reader.read(written + 0.5)["playing"])
        self.assertIsNone(reader.read(written + bridge.STALE_SECONDS + 0.01))

    def test_status_roundtrip_unicode_and_newlines(self):
        bridge.write_status(self.path, {"title": "Regueton: corazon 🎵\nsegunda linea", "playing": "1"})
        values = dict(line.split("=", 1) for line in self.path.read_text(encoding="utf-8").splitlines())
        self.assertEqual(unquote(values["title"]), "Regueton: corazon 🎵\nsegunda linea")
        self.assertFalse(self.path.with_suffix(".tmp").exists())


class LockTests(unittest.TestCase):
    def test_single_instance_and_reopen_after_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.lock"
            first = bridge.BridgeLock(path)
            try:
                with self.assertRaises(OSError):
                    bridge.BridgeLock(path)
            finally:
                first.close()
            second = bridge.BridgeLock(path)
            second.close()


class ConsoleTests(unittest.TestCase):
    def test_disables_quick_edit_without_disabling_ctrl_c(self):
        class Kernel:
            def GetStdHandle(self, which):
                return 123

            def GetConsoleMode(self, handle, mode):
                mode._obj.value = 0x0040 | 0x0001 | 0x0004
                return 1

            def SetConsoleMode(self, handle, mode):
                self.mode = mode
                return 1

        kernel = Kernel()
        self.assertTrue(bridge.disable_console_selection(kernel))
        self.assertEqual(kernel.mode & 0x0040, 0)
        self.assertEqual(kernel.mode & 0x0080, 0x0080)
        self.assertEqual(kernel.mode & 0x0005, 0x0005)

    def test_redirected_console_is_accepted(self):
        class Kernel:
            def GetStdHandle(self, which):
                return 0

            def GetConsoleMode(self, handle, mode):
                return 0

        self.assertFalse(bridge.disable_console_selection(Kernel()))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.pear = FakePear()
        self.controller = bridge.RadioController(self.pear)

    def test_idle_does_not_pause_unrelated_music(self):
        self.controller.step(snapshot(active=False), 0)
        self.controller.step(None, 1)
        self.assertEqual(self.pear.calls, [])

    def test_play_does_not_repeat_each_heartbeat(self):
        self.controller.step(snapshot(), 0)
        self.controller.step(snapshot(frame=2), 0.5)
        self.assertEqual(sum(call[1] == "play" for call in self.pear.calls), 1)
        self.assertEqual(sum(call[1] == "volume" and call[0] == "post" for call in self.pear.calls), 1)

    def test_exit_and_stale_heartbeat_pause_and_restore_volume(self):
        for stopped in (None, snapshot(active=False)):
            with self.subTest(stopped=stopped):
                pear = FakePear()
                controller = bridge.RadioController(pear)
                controller.step(snapshot(), 0)
                controller.step(stopped, 4)
                self.assertIn(("post", "pause", None), pear.calls)
                self.assertEqual(pear.calls[-1], ("post", "volume", {"volume": 73}))
                self.assertFalse(controller.owned)

    def test_lost_pause_is_retried(self):
        self.controller.step(snapshot(), 0)
        self.pear.fail_pause = True
        with self.assertRaises(bridge.PearError):
            self.controller.step(None, 4)
        self.assertTrue(self.controller.owned)
        self.pear.fail_pause = False
        self.controller.step(None, 5)
        self.assertFalse(self.controller.owned)

    def test_next_consumed_once_and_not_replayed_on_restart(self):
        self.controller.step(snapshot(action_id=5, action="next"), 0)
        self.assertNotIn(("post", "next", None), self.pear.calls)
        self.controller.step(snapshot(action_id=6, action="next"), 1)
        self.controller.step(snapshot(action_id=6, action="next", frame=3), 2)
        self.assertEqual(self.pear.calls.count(("post", "next", None)), 1)

    def test_no_zombie_playing_confirmation_without_real_song(self):
        self.pear.song = {}
        self.assertEqual(self.controller.step(snapshot(), 0)["playing"], "0")
        self.pear.song = {"videoId": "abc", "isPaused": True}
        self.assertEqual(self.controller.step(snapshot(), 2)["playing"], "0")

    def test_pause_then_resume(self):
        self.controller.step(snapshot(), 0)
        status = self.controller.step(snapshot(playing=False), 2)
        self.assertEqual(status["playing"], "0")
        status = self.controller.step(snapshot(), 4)
        self.assertEqual(status["playing"], "1")
        self.assertEqual(self.pear.calls.count(("post", "play", None)), 2)

    def test_distance_volume_zero_keeps_track_advancing(self):
        self.controller.step(snapshot(), 0)
        self.controller.step(snapshot(volume=20), 1)
        status = self.controller.step(snapshot(volume=0), 2)
        self.assertEqual(status["playing"], "1")
        self.assertNotIn(("post", "pause", None), self.pear.calls)
        self.assertEqual(self.pear.calls.count(("post", "play", None)), 1)
        self.assertIn(("post", "volume", {"volume": 0}), self.pear.calls)

    def test_session_change_releases_previous_game(self):
        self.controller.step(snapshot(), 0)
        self.pear.calls.clear()
        self.controller.step(snapshot(session="new-game", playing=False), 2)
        self.assertIn(("post", "pause", None), self.pear.calls)
        self.assertFalse(self.controller.owned)

    def test_dead_pear_does_not_repeat_next_after_reconnect(self):
        self.controller.step(snapshot(), 0)
        original_post = self.pear.post

        def uncertain_post(endpoint, data=None):
            original_post(endpoint, data)
            if endpoint == "next":
                raise bridge.PearError("response lost")

        self.pear.post = uncertain_post
        with self.assertRaises(bridge.PearError):
            self.controller.step(snapshot(action_id=1, action="next"), 1)
        self.pear.post = original_post
        self.controller.step(snapshot(action_id=1, action="next"), 3)
        self.assertEqual(self.pear.calls.count(("post", "next", None)), 1)


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                cls.requests.append((self.path, self.headers.get("Authorization"), data))
                if self.path.startswith("/auth/"):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({"accessToken": "test-token"}).encode())
                else:
                    self.send_response(204 if self.headers.get("Authorization") == "Bearer test-token" else 401)
                    self.end_headers()

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_real_http_auth_volume_and_204(self):
        api = bridge.PearAPI(self.server.server_port)
        api.connect()
        self.assertIsNone(api.post("volume", {"volume": 42}))
        self.assertEqual(self.requests[-1][0], "/api/v1/volume")
        self.assertEqual(self.requests[-1][1], "Bearer test-token")
        self.assertEqual(json.loads(self.requests[-1][2]), {"volume": 42})

    def test_401_clears_token(self):
        api = bridge.PearAPI(self.server.server_port)
        api.token = "invalid"
        with self.assertRaises(bridge.PearError):
            api.post("play")
        self.assertIsNone(api.token)


if __name__ == "__main__":
    unittest.main()

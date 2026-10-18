import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from desktop_app import load_settings
from pear_bridge import CONTROL_FILE, STATUS_FILE, BridgeLock, PearError, run_bridge


class SettingsTests(unittest.TestCase):
    def test_missing_or_invalid_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertEqual(load_settings(path)["port"], 26538)
            for content in ("not json", "[]", '{"port":70000,"zomboid_dir":"C:/Zomboid"}'):
                path.write_text(content, encoding="utf-8")
                self.assertEqual(load_settings(path)["port"], 26538)

    def test_custom_folder_and_port_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            expected = {"zomboid_dir": directory, "port": 26539}
            path.write_text(json.dumps(expected), encoding="utf-8")
            self.assertEqual(load_settings(path), expected)


class WorkerTests(unittest.TestCase):
    def test_disconnect_pauses_playback_restores_volume_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "Lua"
            folder.mkdir()
            (folder / CONTROL_FILE).write_text(
                "protocol=1\nsession=desktop-test\nframe=1\nactive=1\nplaying=1\n"
                "volume=42\nvehicle=12\naction_id=0\naction=none\ncommit=1\n", encoding="utf-8")
            calls = []
            stop = threading.Event()
            result = []

            class API:
                token = None

                def connect(self):
                    self.token = "test-token"

                def get(self, endpoint):
                    if endpoint == "volume":
                        return {"state": 73}
                    return {"videoId": "abcdef12345", "title": "Test song", "isPaused": False}

                def post(self, endpoint, data=None):
                    calls.append((endpoint, data))

            def status(value):
                if value.get("playing") == "1":
                    stop.set()

            worker = threading.Thread(target=lambda: result.append(run_bridge(
                directory, stop_event=stop, on_status=status, api_factory=lambda port: API())))
            worker.start()
            worker.join(timeout=4)
            if worker.is_alive():
                stop.set()
                worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result, [0])
            self.assertIn(("play", None), calls)
            self.assertIn(("pause", None), calls)
            self.assertEqual(calls[-1], ("volume", {"volume": 73}))
            values = dict(line.split("=", 1) for line in (folder / STATUS_FILE).read_text().splitlines())
            self.assertEqual(unquote(values["message"]), "Bridge stopped.")
            lock = BridgeLock(folder / "PearCarRadio.lock")
            lock.close()

    def test_offline_retry_can_be_cancelled_without_waiting_for_sleep(self):
        with tempfile.TemporaryDirectory() as directory:
            stop = threading.Event()
            result = []

            class API:
                token = None

                def connect(self):
                    raise PearError("offline")

            worker = threading.Thread(target=lambda: result.append(run_bridge(
                directory, stop_event=stop, on_status=lambda value: stop.set(),
                api_factory=lambda port: API())))
            worker.start()
            worker.join(timeout=2)
            if worker.is_alive():
                stop.set()
                worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result, [0])

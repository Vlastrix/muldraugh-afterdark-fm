import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import tkinter as tk
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from desktop_app import ConnectorWindow, load_settings
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


class UnifiedWindowTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()
        self.temporary = tempfile.TemporaryDirectory()
        self.window = ConnectorWindow(self.root, settings_path=Path(self.temporary.name) / 'settings.json')
        self.window.directory.set(self.temporary.name)
        self.window.multiplayer.folder.set(self.temporary.name)

    def pump(self, predicate, timeout=3):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():
                return True
            self.root.update()
            time.sleep(0.01)
        return predicate()

    def tearDown(self):
        if not hasattr(self,'window'):
            return
        self.window.stop_event.set()
        self.window.multiplayer.stop_event.set()
        for worker in (self.window.worker,self.window.multiplayer.worker):
            if worker:
                worker.join(timeout=4)
        self.window.remove_handlers()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.temporary.cleanup()

    def test_embedded_modes_start_idle_and_cannot_run_together(self):
        self.assertTrue(self.window.multiplayer.embedded)
        self.assertIsNone(self.window.worker)
        self.assertIsNone(self.window.multiplayer.worker)
        self.assertFalse(any(isinstance(child,tk.Toplevel) for child in self.root.winfo_children()))
        def solo(folder,port,stop,callback):
            stop.wait(3)
            return 0
        def multiplayer(folder,process,stop,*callbacks):
            stop.wait(3)
        with patch('desktop_app.run_bridge',side_effect=solo) as sp, \
                patch('radio_audio.run_radio',side_effect=multiplayer) as mp, \
                patch('desktop_app.messagebox.showinfo'):
            self.window.start()
            self.assertTrue(self.window.singleplayer_running())
            self.assertEqual(str(self.window.multiplayer.start_button['state']),'disabled')
            self.window.multiplayer.start()
            mp.assert_not_called()
            self.window.stop()
            self.assertTrue(self.pump(lambda: str(self.window.multiplayer.start_button['state'])=='normal'))
            self.window.multiplayer.start()
            self.assertTrue(self.pump(lambda: mp.called))
            self.assertEqual(str(self.window.start_button['state']),'disabled')
            self.window.start()
            self.assertEqual(sp.call_count,1)
            self.window.multiplayer.stop()
            self.assertTrue(self.pump(lambda: str(self.window.start_button['state'])=='normal'))

    def test_close_waits_for_multiplayer_cleanup_before_destroying_shared_window(self):
        stopping,release=threading.Event(),threading.Event()
        def multiplayer(folder,process,stop,*callbacks):
            stop.wait(3)
            stopping.set()
            release.wait(3)
        try:
            with patch('radio_audio.run_radio',side_effect=multiplayer), \
                    patch.object(self.root,'destroy',wraps=self.root.destroy) as destroy:
                self.window.multiplayer.start()
                self.window.close()
                self.assertTrue(stopping.wait(1))
                self.root.update()
                destroy.assert_not_called()
                release.set()
                self.assertTrue(self.pump(lambda: destroy.called))
                destroy.assert_called_once()
        finally:
            release.set()


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

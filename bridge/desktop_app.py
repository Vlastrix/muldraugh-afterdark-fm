"""Windows Connector UI. Players run the bundled executable, not Python."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from pear_bridge import run_bridge

APP_NAME = "Afterdark FM Connector"
VERSION = "0.5.1"
GUIDE_URL = "https://github.com/Vlastrix/muldraugh-afterdark-fm#player-setup"
SETTINGS_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MuldraughAfterdarkFM" / "settings.json"


def load_settings(path=SETTINGS_PATH):
    defaults = {"zomboid_dir": str(Path.home() / "Zomboid"), "port": 26538}
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        folder = values.get("zomboid_dir")
        port = values.get("port")
        if isinstance(folder, str) and folder and isinstance(port, int) and 1 <= port <= 65535:
            return {"zomboid_dir": folder, "port": port}
    except (OSError, ValueError, AttributeError):
        pass
    return defaults


class WindowLogHandler(logging.Handler):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def emit(self, record):
        self.events.put(("log", self.format(record)))


class ConnectorWindow:
    def __init__(self, root, auto_start=True, settings_path=SETTINGS_PATH):
        self.root = root
        self.settings_path = settings_path
        self.events = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.closing = False
        self.log_handler = None
        self.file_handler = None
        settings = load_settings(settings_path)
        self.directory = tk.StringVar(value=settings["zomboid_dir"])
        self.port = tk.StringVar(value=str(settings["port"]))
        self.connection = tk.StringVar(value="Not connected")
        self.message = tk.StringVar(value="Open Pear Desktop, then authorize this connector when prompted.")
        self.song = tk.StringVar(value="No song selected")
        self.artist = tk.StringVar(value="")
        self.root.title(APP_NAME)
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets" / "app.ico"
        if icon.is_file() and sys.platform == "win32":
            self.root.iconbitmap(str(icon))
        self.root.geometry("640x540")
        self.root.minsize(590, 490)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Station.TLabel", font=("Segoe UI", 12), foreground="#427a58")
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"))
        body = ttk.Frame(root, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text="94.46 MHz  /  Windows Connector", style="Station.TLabel").pack(anchor="w", pady=(2, 18))
        ttk.Label(body, textvariable=self.connection, style="Status.TLabel").pack(anchor="w")
        ttk.Label(body, textvariable=self.message, wraplength=565).pack(anchor="w", pady=(8, 14))
        ttk.Label(body, textvariable=self.song, font=("Segoe UI", 12, "bold"), wraplength=560).pack(anchor="w")
        ttk.Label(body, textvariable=self.artist, wraplength=560).pack(anchor="w", pady=(2, 14))
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(0, 12))
        self.start_button = ttk.Button(controls, text="Connect", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Disconnect", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(controls, text="Setup guide", command=lambda: webbrowser.open(GUIDE_URL)).pack(side="right")
        ttk.Label(body, text="Keep this window open while playing. Control music from your car radio.", wraplength=560).pack(anchor="w")
        self.settings = ttk.LabelFrame(body, text="Settings (defaults work for most players)", padding=10)
        self.settings.pack(fill="x", pady=(16, 10))
        self.settings.columnconfigure(1, weight=1)
        ttk.Label(self.settings, text="Zomboid folder").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.directory_entry = ttk.Entry(self.settings, textvariable=self.directory)
        self.directory_entry.grid(row=0, column=1, sticky="ew")
        self.browse_button = ttk.Button(self.settings, text="Browse", command=self.browse)
        self.browse_button.grid(row=0, column=2, padx=(6, 0))
        ttk.Label(self.settings, text="Pear API port").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.port_entry = ttk.Entry(self.settings, textvariable=self.port, width=8)
        self.port_entry.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.details = tk.Text(body, height=5, font=("Consolas", 9), state="disabled", wrap="word")
        self.details.pack(fill="both", expand=True)
        ttk.Label(body, text="v{}  ·  Singleplayer only".format(VERSION)).pack(anchor="e", pady=(8, 0))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.poll)
        if auto_start:
            self.root.after(200, self.start)

    def browse(self):
        selected = filedialog.askdirectory(title="Select your Zomboid user folder", initialdir=self.directory.get())
        if selected:
            self.directory.set(selected)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            port = int(self.port.get())
            if not 1 <= port <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
            directory = Path(self.directory.get()).expanduser()
            if not directory.is_absolute():
                raise ValueError("Choose an absolute Zomboid user folder path.")
            (directory / "Lua").mkdir(parents=True, exist_ok=True)
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(json.dumps({"zomboid_dir": str(directory), "port": port}), encoding="utf-8")
            self.configure_logging(directory)
        except (ValueError, OSError) as error:
            messagebox.showerror(APP_NAME, str(error))
            return
        self.stop_event = threading.Event()
        self.connection.set("Connecting to Pear...")
        self.message.set("Accept PZPearCarRadio in Pear if an authorization window appears.")
        self.set_running(True)

        def work():
            result = 1
            try:
                result = run_bridge(directory, port, self.stop_event,
                                    lambda status: self.events.put(("status", status)))
            except Exception:
                logging.getLogger("pear-radio").exception("Connector stopped unexpectedly")
            finally:
                self.events.put(("stopped", result))

        self.worker = threading.Thread(target=work, daemon=True, name="AfterdarkBridge")
        self.worker.start()

    def configure_logging(self, directory):
        self.remove_handlers()
        logger = logging.getLogger("pear-radio")
        logger.setLevel(logging.INFO)
        self.log_handler = WindowLogHandler(self.events)
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        self.file_handler = RotatingFileHandler(directory / "Lua" / "AfterdarkBridge.log", maxBytes=512000, backupCount=2, encoding="utf-8")
        self.file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(self.log_handler)
        logger.addHandler(self.file_handler)

    def remove_handlers(self):
        for handler in (self.log_handler, self.file_handler):
            if handler:
                logging.getLogger("pear-radio").removeHandler(handler)
                handler.close()
        self.log_handler = self.file_handler = None

    def set_running(self, running):
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        for widget in (self.directory_entry, self.browse_button, self.port_entry):
            widget.configure(state="disabled" if running else "normal")

    def stop(self):
        self.stop_event.set()
        self.connection.set("Disconnecting...")
        self.message.set("Finishing the Pear request and pausing controlled playback. Close any Pear authorization dialog if needed.")
        self.stop_button.configure(state="disabled")

    def close(self):
        self.closing = True
        if self.worker and self.worker.is_alive():
            self.stop()
        else:
            self.remove_handlers()
            self.root.destroy()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status" and not self.stop_event.is_set():
                    self.connection.set("Pear connected" if value.get("connected") == "1" else "Pear not connected")
                    self.message.set(value.get("message", ""))
                    self.song.set(value.get("title") or "No song selected")
                    self.artist.set(value.get("artist", ""))
                elif kind == "log":
                    self.details.configure(state="normal")
                    self.details.insert("end", value + "\n")
                    if int(self.details.index("end-1c").split(".")[0]) > 150:
                        self.details.delete("1.0", "30.0")
                    self.details.see("end")
                    self.details.configure(state="disabled")
                elif kind == "stopped":
                    self.connection.set("Disconnected" if value == 0 else "Could not start connector")
                    self.message.set("Open Pear and press Connect." if value == 0 else "Check the details below. Another connector may already be running.")
                    self.set_running(False)
                    self.remove_handlers()
        except queue.Empty:
            pass
        if self.closing and (not self.worker or not self.worker.is_alive()):
            self.remove_handlers()
            self.root.destroy()
            return
        self.root.after(100, self.poll)


def main():
    root = tk.Tk()
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        # Packaged build smoke test. No user settings, network or game changes.
        root.withdraw()
        ConnectorWindow(root, auto_start=False)
        root.update()
        report = {"frozen": bool(getattr(sys, "frozen", False)), "version": VERSION,
                  "tk": tk.TkVersion, "window_created": True}
        Path(sys.argv[2]).write_text(json.dumps(report), encoding="utf-8")
        root.destroy()
        return
    ConnectorWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()

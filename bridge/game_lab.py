"""Explicit audio test over Zomboid's mod-command connection. No external sockets."""
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from audio_devices import AudioOutput, PearCapture, pear_processes
from audio_stream import FRAMES, RATE
from game_audio import GameBridge


class GameLabWindow:
    def __init__(self, root, zomboid_dir=None, radio=False):
        self.root = root
        self.events = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.closing = False
        self.output = None
        self.processes = []
        self.role = tk.StringVar(value='radio' if radio else 'listen')
        self.share_capable = tk.BooleanVar(value=False)
        self.local_gain = 0.5
        self.folder = tk.StringVar(value=str(zomboid_dir or Path.home() / 'Zomboid'))
        self.process = tk.StringVar()
        self.status = tk.StringVar(value='Join the same server with the experimental mod installed, then press Start.')
        self.metrics = tk.StringVar(value='Waiting for game signal.')
        root.title('Afterdark FM Connector - Game network lab')
        root.geometry('820x600')
        root.minsize(720, 520)
        body = ttk.Frame(root, padding=22)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Game network lab', font=('Segoe UI', 21, 'bold')).pack(anchor='w')
        ttk.Label(body, text='Experimental - audio through Zomboid, without an extra VPN or audio port', wraplength=730).pack(anchor='w', pady=(4, 12))
        ttk.Label(body, text='Radio mode follows car and placed radios automatically. Only a music owner needs Pear.\nListen, Send test tone and Share my Pear are the separate shared-channel transport tests.', wraplength=730).pack(anchor='w')
        roles = ttk.Frame(body)
        roles.pack(fill='x', pady=14)
        self.radios = []
        for label, role in [('Radio', 'radio'), ('Listen', 'listen'), ('Send test tone', 'tone'), ('Share my Pear', 'share')]:
            button = ttk.Radiobutton(roles, text=label, variable=self.role, value=role, command=self.refresh)
            button.pack(side='left', padx=(0, 20))
            self.radios.append(button)
        self.share_check = ttk.Checkbutton(body, text='Allow Use my Pear in Radio mode (requires Pear API authorization)',
                                          variable=self.share_capable, command=self.refresh)
        self.share_check.pack(anchor='w', pady=(0, 10))
        settings = ttk.Frame(body)
        settings.pack(fill='x')
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text='Zomboid user folder').grid(row=0, column=0, sticky='w')
        self.folder_entry = ttk.Entry(settings, textvariable=self.folder)
        self.folder_entry.grid(row=0, column=1, sticky='ew', padx=10)
        self.browse_button = ttk.Button(settings, text='Browse', command=self.browse)
        self.browse_button.grid(row=0, column=2)
        ttk.Label(settings, text='Pear process').grid(row=1, column=0, sticky='w', pady=12)
        self.process_combo = ttk.Combobox(settings, textvariable=self.process, state='disabled')
        self.process_combo.grid(row=1, column=1, sticky='ew', padx=10)
        self.refresh_button = ttk.Button(settings, text='Refresh', command=self.refresh, state='disabled')
        self.refresh_button.grid(row=1, column=2)
        controls = ttk.Frame(body)
        controls.pack(fill='x', pady=10)
        self.start_button = ttk.Button(controls, text='Start', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(controls, text='Stop', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=10)
        ttk.Label(body, text='Listener volume').pack(anchor='w')
        self.volume = ttk.Scale(body, from_=0, to=1, command=self.change_gain)
        self.volume.set(0.5)
        self.volume.pack(fill='x', pady=6)
        ttk.Label(body, textvariable=self.status, wraplength=730).pack(anchor='w', pady=(10, 6))
        ttk.Label(body, textvariable=self.metrics, wraplength=730).pack(anchor='w')
        ttk.Label(body, text='Use the test mod on both clients AND the server. Keep the singleplayer bridge disconnected.\nIn Radio mode, tune a powered radio to Afterdark FM, then press Use my Pear.\nThe owner currently hears Pear directly; distance gain applies to remote listeners.', wraplength=730).pack(anchor='w', pady=14)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def browse(self):
        folder = filedialog.askdirectory(initialdir=self.folder.get())
        if folder:
            self.folder.set(folder)

    def refresh(self):
        sharing = self.role.get() == 'share' or (self.role.get() == 'radio' and self.share_capable.get())
        self.process_combo.configure(state='readonly' if sharing else 'disabled')
        self.refresh_button.configure(state='normal' if sharing else 'disabled')
        if sharing:
            try:
                self.processes = pear_processes()
                self.process_combo['values'] = ['{} (PID {})'.format(p['name'], p['pid']) for p in self.processes]
                if self.processes:
                    self.process_combo.current(0)
                else:
                    self.process.set('')
                    self.status.set('Open Pear Desktop and press Refresh.')
            except Exception as error:
                self.status.set(str(error))

    def change_gain(self, value):
        self.local_gain = float(value)
        if self.output is not None:
            self.output.gain = float(value)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        role, folder, process = self.role.get(), Path(self.folder.get()).expanduser(), None
        try:
            if not folder.is_absolute():
                raise ValueError('Choose an absolute Zomboid user folder.')
            if role == 'share' or (role == 'radio' and self.share_capable.get()):
                index = self.process_combo.current()
                if index < 0:
                    raise ValueError('Select a Pear process first.')
                process = self.processes[index]
        except (ValueError, IndexError) as error:
            messagebox.showerror('Afterdark FM Connector', str(error))
            return
        self.stop_event = threading.Event()
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        for widget in self.radios + [self.share_check, self.folder_entry, self.browse_button, self.process_combo, self.refresh_button]:
            widget.configure(state='disabled')
        gain = float(self.volume.get())
        self.status.set('Waiting for the experimental mod and a game server...')

        def work():
            bridge = output = None
            capture_stop = threading.Event()
            capture_worker = None
            source_frames = queue.Queue(maxsize=8)
            errors = queue.Queue()
            error = None
            try:
                if role == 'radio':
                    from radio_audio import run_radio
                    run_radio(folder, process, self.stop_event,
                              lambda state: self.events.put(('state', state)),
                              lambda output: setattr(self, 'output', output), lambda: self.local_gain)
                    return
                bridge = GameBridge(folder, role)
                if role == 'listen':
                    output = AudioOutput()
                    output.gain = gain
                    output.start()
                    self.output = output
                next_report = next_tone = time.monotonic()
                tone_position = 0
                while not self.stop_event.is_set():
                    state = bridge.heartbeat()
                    if role == 'listen':
                        for frame in bridge.receive():
                            output.put(frame)
                    elif state and state.get('status') == 'sending':
                        if role == 'tone' and time.monotonic() >= next_tone:
                            import numpy as np
                            wave = (0.04 * 32767 * np.sin(2 * np.pi * 440 * (np.arange(FRAMES) + tone_position) / RATE)).astype('<i2')
                            tone_position += FRAMES
                            bridge.publish(np.repeat(wave[:, None], 2, axis=1).tobytes())
                            next_tone = max(next_tone + 0.02, time.monotonic())
                        elif role == 'share':
                            if capture_worker is None:
                                def capture_audio():
                                    capture = None
                                    try:
                                        capture = PearCapture(process['pid'], process['create_time'])
                                        def put(pcm):
                                            try:
                                                source_frames.put_nowait(pcm)
                                            except queue.Full:
                                                try:
                                                    source_frames.get_nowait()
                                                except queue.Empty:
                                                    pass
                                                source_frames.put_nowait(pcm)
                                        capture.run(capture_stop, put)
                                    except Exception as exception:
                                        errors.put(exception)
                                    finally:
                                        if capture:
                                            capture.close()
                                capture_worker = threading.Thread(target=capture_audio, daemon=True, name='AfterdarkGameCapture')
                                capture_worker.start()
                            try:
                                bridge.publish(source_frames.get_nowait())
                            except queue.Empty:
                                pass
                    else:
                        # Never retain buffered audio or encoder state across a lost source session.
                        bridge.pause_source()
                        while not source_frames.empty():
                            try:
                                source_frames.get_nowait()
                            except queue.Empty:
                                break
                    if not errors.empty():
                        raise errors.get_nowait()
                    if time.monotonic() >= next_report:
                        self.events.put(('state', (state, bridge.sent, bridge.received, bridge.dropped)))
                        next_report = time.monotonic() + 0.25
                    self.stop_event.wait(0.004)
            except Exception as exception:
                error = str(exception)
            finally:
                capture_stop.set()
                if capture_worker:
                    capture_worker.join(timeout=3)
                for resource in (output, bridge):
                    if resource:
                        try:
                            resource.close()
                        except Exception as exception:
                            error = error or str(exception)
                self.output = None
                self.events.put(('finished', error))

        self.worker = threading.Thread(target=work, daemon=True, name='AfterdarkGameBridge')
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.status.set('Stopping game audio...')
        self.stop_button.configure(state='disabled')

    def close(self):
        self.closing = True
        self.stop()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'state' and not self.stop_event.is_set():
                    state, sent, received, dropped = value
                    labels = {'waiting': 'Waiting for a source.', 'sending': 'Sending through the game connection.',
                              'connecting': 'Waiting for server transport. Check that the test mod is enabled on the server.',
                              'listening': 'Receiving through the game connection.', 'busy': 'Another player is sharing. Stop and choose Listen.',
                              'full': 'The test channel is full.'}
                    self.status.set(state.get('radio_message') or labels.get(state.get('status'), 'Waiting for game signal.') if state else 'No game signal. Join a server with the experimental mod installed.')
                    self.metrics.set('Prepared: {} | Game sent: {} | Received: {} | Confirmed echo: {} | Skipped local/game: {}/{} | RTT: {} ms | Server rejected: {} | Room changes: {} | Owner: {}'.format(
                        sent, (state or {}).get('sent', '0'), received, (state or {}).get('confirmed', '0'), dropped, (state or {}).get('dropped', '0'),
                        (state or {}).get('rtt', '?'), (state or {}).get('rejected', '0'), (state or {}).get('room_changes', '0'), (state or {}).get('owner', '')))
                elif kind == 'finished':
                    self.status.set('Game audio stopped.' if value is None else 'Could not run game audio: ' + value)
                    self.start_button.configure(state='normal')
                    self.stop_button.configure(state='disabled')
                    for widget in self.radios + [self.share_check, self.folder_entry, self.browse_button]:
                        widget.configure(state='normal')
                    self.refresh()
        except queue.Empty:
            pass
        if self.closing and (not self.worker or not self.worker.is_alive()):
            self.root.destroy()
            return
        self.root.after(100, self.poll)

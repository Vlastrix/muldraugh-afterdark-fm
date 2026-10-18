"""Two-computer audio prototype. No game integration or listener Pear dependency."""
import logging
import queue
import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from audio_devices import AudioOutput, PearCapture, pear_processes
from audio_stream import AudioHost, receive_audio


def local_address():
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
        return next((address for address in addresses if not address.startswith('127.')), '127.0.0.1')
    except OSError:
        return '127.0.0.1'


class AudioLabWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.closing = False
        self.output = None
        self.processes = []
        self.role = tk.StringVar(value='listen')
        self.address = tk.StringVar(value=local_address())
        self.port = tk.StringVar(value='26539')
        self.invite = tk.StringVar()
        self.process = tk.StringVar()
        self.status = tk.StringVar(value='Choose Listen or Share my Pear, then press Start.')
        self.level = tk.StringVar(value='Capture level: --')
        root.title('Afterdark FM Connector - Audio lab')
        root.geometry('760x600')
        root.minsize(700, 580)
        body = ttk.Frame(root, padding=22)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Afterdark FM Connector', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(body, text='Experimental audio lab - not connected to Zomboid', foreground='#935400').pack(anchor='w', pady=(4, 12))
        ttk.Label(body, text='Test on the same LAN or an existing private VPN. No automatic Internet connection or game controls yet.', wraplength=690).pack(anchor='w')
        roles = ttk.Frame(body)
        roles.pack(fill='x', pady=12)
        self.listen_radio = ttk.Radiobutton(roles, text='Listen (no Pear required)', variable=self.role, value='listen', command=self.update_role)
        self.listen_radio.pack(side='left')
        self.share_radio = ttk.Radiobutton(roles, text='Share my Pear', variable=self.role, value='share', command=self.update_role)
        self.share_radio.pack(side='left', padx=16)
        sender = ttk.LabelFrame(body, text='Sender settings', padding=10)
        sender.pack(fill='x', pady=(0, 10))
        sender.columnconfigure(1, weight=1)
        ttk.Label(sender, text='Pear process').grid(row=0, column=0, sticky='w')
        self.process_combo = ttk.Combobox(sender, textvariable=self.process, state='readonly')
        self.process_combo.grid(row=0, column=1, sticky='ew', padx=8)
        self.refresh_button = ttk.Button(sender, text='Refresh', command=self.refresh)
        self.refresh_button.grid(row=0, column=2)
        ttk.Label(sender, text='Your LAN/VPN address').grid(row=1, column=0, sticky='w', pady=(8, 0))
        self.address_entry = ttk.Entry(sender, textvariable=self.address)
        self.address_entry.grid(row=1, column=1, sticky='ew', padx=8, pady=(8, 0))
        ttk.Label(sender, text='Port').grid(row=2, column=0, sticky='w', pady=(8, 0))
        self.port_entry = ttk.Entry(sender, textvariable=self.port, width=8)
        self.port_entry.grid(row=2, column=1, sticky='w', padx=8, pady=(8, 0))
        ttk.Label(body, text='Invitation: sender copies it; listener pastes it here. Treat it as a private session key.').pack(anchor='w')
        self.invite_entry = ttk.Entry(body, textvariable=self.invite)
        self.invite_entry.pack(fill='x', pady=(6, 8))
        controls = ttk.Frame(body)
        controls.pack(fill='x')
        self.start_button = ttk.Button(controls, text='Start', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(controls, text='Stop', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        ttk.Button(controls, text='Copy invitation', command=self.copy_invite).pack(side='right')
        ttk.Label(body, text='Listener volume (does not change the sender\'s Pear)').pack(anchor='w', pady=(14, 0))
        self.volume = ttk.Scale(body, from_=0, to=1, command=self.change_gain)
        self.volume.set(0.5)
        self.volume.pack(fill='x', pady=4)
        ttk.Label(body, textvariable=self.status, wraplength=690).pack(anchor='w', pady=(10, 6))
        ttk.Label(body, textvariable=self.level).pack(anchor='w')
        ttk.Label(body, text='Close the normal Connector bridge before sharing. Do not mute Pear: capture may follow its volume.\nOnly Pear is captured; there is no desktop-wide capture fallback. Listeners hear the stream with some delay.', wraplength=690).pack(anchor='w', pady=12)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        self.update_role()

    def refresh(self):
        try:
            self.processes = pear_processes()
            self.process_combo['values'] = ['{} (PID {})'.format(p['name'], p['pid']) for p in self.processes]
            self.process_combo.current(0) if self.processes else self.process.set('')
            if not self.processes:
                self.status.set('No Pear process found. Open Pear Desktop and press Refresh.')
        except Exception as error:
            self.status.set('Cannot list Pear processes: {}'.format(error))

    def update_role(self):
        sharing = self.role.get() == 'share'
        self.process_combo.configure(state='readonly' if sharing else 'disabled')
        for widget in (self.refresh_button, self.address_entry, self.port_entry):
            widget.configure(state='normal' if sharing else 'disabled')
        if sharing:
            self.refresh()

    def copy_invite(self):
        if self.invite.get():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.invite.get())

    def change_gain(self, value):
        if self.output:
            self.output.gain = float(value)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        sharing = self.role.get() == 'share'
        try:
            if sharing:
                index = self.process_combo.current()
                if index < 0:
                    raise ValueError('Open Pear, press Refresh and select its process.')
                process = self.processes[index]
                port = int(self.port.get())
                if not 1 <= port <= 65535:
                    raise ValueError('Port must be between 1 and 65535.')
                address = self.address.get().strip()
                if not address:
                    raise ValueError('Enter an address the listener can reach on your LAN or VPN.')
                invitation = None
                self.invite.set('')
            else:
                from audio_stream import parse_invite
                invitation = self.invite.get().strip()
                parse_invite(invitation)
        except (ValueError, IndexError) as error:
            messagebox.showerror('Afterdark FM Connector', str(error))
            return
        self.stop_event = threading.Event()
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        for widget in (self.listen_radio, self.share_radio, self.process_combo, self.refresh_button, self.address_entry, self.port_entry):
            widget.configure(state='disabled')
        self.status.set('Starting process capture...' if sharing else 'Connecting to sender...')
        gain = float(self.volume.get())

        def work():
            host = None
            output = None
            capture = None
            error = None
            status = lambda message: self.events.put(('status', message))
            try:
                if sharing:
                    # Native capture stays on its owning worker thread.
                    capture = PearCapture(process['pid'], process['create_time'])
                    host = AudioHost(status)
                    invite = host.start(address, port)
                    self.events.put(('invite', invite))
                    status('Sharing Pear audio. Send the invitation to a listener on your LAN/VPN.')
                    capture.run(self.stop_event, host.publish, lambda value: self.events.put(('level', value)))
                else:
                    output = AudioOutput()
                    output.gain = gain
                    self.output = output
                    output.start()
                    receive_audio(invitation, self.stop_event, output.put, status)
            except Exception as exception:
                if not self.stop_event.is_set():
                    error = str(exception)
                    logging.getLogger('pear-radio').exception('Audio lab stopped')
            finally:
                for resource in (host, capture, output):
                    if resource is not None:
                        try:
                            resource.close()
                        except Exception as cleanup_error:
                            logging.getLogger('pear-radio').exception('Could not finish audio cleanup')
                            error = error or str(cleanup_error)
                self.output = None
                self.events.put(('finished', error))

        self.worker = threading.Thread(target=work, daemon=True, name='AfterdarkAudioLab')
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.status.set('Stopping audio...')
        self.stop_button.configure(state='disabled')

    def close(self):
        self.closing = True
        self.stop()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status' and not self.stop_event.is_set():
                    self.status.set(value)
                elif kind == 'invite':
                    self.invite.set(value)
                elif kind == 'level':
                    self.level.set('Capture peak: {:.1f}%'.format(value * 100))
                elif kind == 'finished':
                    self.status.set('Audio stopped.' if value is None else 'Could not stream audio: ' + value)
                    self.start_button.configure(state='normal')
                    self.stop_button.configure(state='disabled')
                    self.listen_radio.configure(state='normal')
                    self.share_radio.configure(state='normal')
                    self.update_role()
        except queue.Empty:
            pass
        if self.closing and (not self.worker or not self.worker.is_alive()):
            self.root.destroy()
            return
        self.root.after(100, self.poll)

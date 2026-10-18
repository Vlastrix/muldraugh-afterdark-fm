"""Radio session playback and capture; HTTP never blocks the audio transport loop."""
import queue
import threading
import time

from audio_devices import AudioOutput, PearCapture
from game_audio import GameBridge, read_snapshot
from pear_bridge import PearAPI, PearError


class PearRadioControl:
    def __init__(self, api):
        self.api = api
        self.room = None
        self.desired = None
        self.command = None
        self.saved_volume = None
        self.volume = None

    def step(self, state):
        owning = bool(state and state.get('owning') == '1' and state.get('room'))
        if not owning:
            if self.room:
                self.api.post('pause')
                if self.saved_volume is not None:
                    self.api.post('volume', {'volume': self.saved_volume})
                self.room = None
                self.desired = None
                self.saved_volume = self.volume = None
            return dict(playing='0', report_room='', command_ack=0, title='', artist='')
        room = state['room']
        volume = int(state['volume'])
        if not 0 <= volume <= 100:
            raise ValueError('Invalid shared radio volume.')
        if self.room is None:
            original = (self.api.get('volume') or {}).get('state')
            if isinstance(original, (int, float)) and not isinstance(original, bool) and 0 <= original <= 100:
                self.saved_volume = original
        self.room = room
        if volume != self.volume:
            self.api.post('volume', {'volume': volume})
            self.volume = volume
        desired = (room, state.get('paused') == '1')
        if desired != self.desired:
            self.room = room
            self.api.post('pause' if desired[1] else 'play')
            self.desired = desired
        command_id = int(state.get('command_id', 0))
        key = (room, command_id)
        action = state.get('action')
        if command_id > 0 and key != self.command and action in ('previous', 'next', 'pause', 'play'):
            # Consume before HTTP, so a lost response cannot repeat Next.
            self.command = key
            self.api.post(action)
        song = self.api.get('song') or {}
        return dict(report_room=room, command_ack=command_id,
                    playing='1' if song.get('videoId') and song.get('isPaused') is False else '0',
                    title=str(song.get('title', ''))[:240], artist=str(song.get('artist', ''))[:160])


def run_radio(folder, process, stop, on_state, set_output, gain):
    bridge = GameBridge(folder, 'radio')
    output = None
    api_stop = threading.Event()
    capture_stop = threading.Event()
    frames = queue.Queue(maxsize=8)
    failures = queue.Queue()
    shared = dict(desired=None, report={}, report_at=0.0)
    lock = threading.Lock()
    api_worker = capture_worker = None

    def pear_worker():
        api = PearAPI()
        controller = PearRadioControl(api)
        try:
            while not api_stop.is_set():
                try:
                    if not api.token:
                        api.connect()
                    if api_stop.is_set():
                        break
                    with lock:
                        desired = shared['desired']
                    report = controller.step(desired)
                    with lock:
                        shared['report'] = dict(report, ready='1')
                        shared['report_at'] = time.monotonic()
                except (PearError, ValueError) as error:
                    with lock:
                        shared['report'] = dict(ready='0', playing='0', message=str(error))
                        shared['report_at'] = time.monotonic()
                    api_stop.wait(1)
                api_stop.wait(0.2)
        finally:
            try:
                controller.step(None)
            except PearError:
                pass

    def capture_audio():
        capture = None
        try:
            capture = PearCapture(process['pid'], process['create_time'])
            def put(pcm):
                try:
                    frames.put_nowait(pcm)
                except queue.Full:
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        pass
                    frames.put_nowait(pcm)
            capture.run(capture_stop, put)
        except Exception as error:
            failures.put(error)
        finally:
            if capture:
                capture.close()

    try:
        output = AudioOutput()
        output.gain = 0
        output.start()
        set_output(output)
        if process:
            api_worker = threading.Thread(target=pear_worker, daemon=True, name='AfterdarkRadioPear')
            api_worker.start()
        info, deadline, last_room, next_report = None, 0, None, 0
        while not stop.is_set():
            now = time.time()
            state = bridge.heartbeat()
            path = bridge.folder / 'AfterdarkRadio.info.txt'
            incoming = read_snapshot(path, max_age=0.8, now=now)
            if incoming and incoming.get('client') == bridge.client:
                try:
                    deadline = min(now + 0.4, path.stat().st_mtime + 0.8)
                    info = incoming
                except OSError:
                    pass
            if now > deadline or not state or not info or info.get('room') != state.get('room'):
                info = None
            owning = bool(info and info.get('owning') == '1' and state.get('status') == 'sending')
            with lock:
                shared['desired'] = info if owning else None
                report = dict(shared['report']) if time.monotonic()-shared['report_at'] < 2.5 else {}
            bridge.report = {key: report.get(key, default) for key, default in (
                ('ready', '0'), ('playing', '0'), ('report_room', ''), ('command_ack', 0), ('title', ''), ('artist', ''))}
            room = state.get('room') if state else None
            if room != last_room:
                output.buffer.clear()
                last_room = room
            local_gain = max(0, min(1, float(info.get('gain', 0)))) if info else 0
            output.gain = local_gain * gain() if not owning and not (info and info.get('paused') == '1') else 0
            for pcm in bridge.receive():
                output.put(pcm)
            if owning and process and report.get('ready') == '1' and info.get('paused') != '1':
                if capture_worker is None:
                    capture_worker = threading.Thread(target=capture_audio, daemon=True, name='AfterdarkRadioCapture')
                    capture_worker.start()
                try:
                    bridge.publish(frames.get_nowait())
                except queue.Empty:
                    pass
            else:
                bridge.pause_source()
                while not frames.empty():
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        break
            if not failures.empty():
                raise failures.get_nowait()
            if time.monotonic() >= next_report:
                display = dict(state or {})
                if report.get('message'):
                    display['radio_message'] = report['message']
                on_state((display, bridge.sent, bridge.received, bridge.dropped))
                next_report = time.monotonic()+0.25
            stop.wait(0.004)
    finally:
        api_stop.set()
        capture_stop.set()
        try:
            bridge.close()
        finally:
            try:
                if output:
                    output.close()
            finally:
                for worker in (capture_worker, api_worker):
                    if worker:
                        worker.join(timeout=3)

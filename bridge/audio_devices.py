"""Windows process capture and local output for the experimental audio lab."""
import sys
import time

from audio_stream import CHANNELS, FRAMES, LiveBuffer, PCM_BYTES, RATE, SILENCE

PEAR_NAMES = {'pear.exe', 'pear desktop.exe', 'pear-desktop.exe', 'youtube music.exe', 'youtube-music.exe'}


def pear_processes():
    import psutil
    found = {}
    for process in psutil.process_iter(['pid', 'name', 'ppid', 'create_time']):
        if (process.info['name'] or '').lower() in PEAR_NAMES:
            found[process.pid] = process.info
    return [info for info in found.values() if info['ppid'] not in found]


class PearCapture:
    """Reject system-wide fallback explicitly, even if the capture library supports it."""
    def __init__(self, pid, expected_start=None):
        if sys.platform != 'win32' or sys.getwindowsversion().build < 20348:
            raise RuntimeError('Process capture requires Windows build 20348 or later (Windows 11 recommended).')
        import psutil
        process = psutil.Process(pid)
        self.process = process
        if expected_start is not None and process.create_time() != expected_start:
            raise RuntimeError('Pear restarted. Refresh the process list and try again.')
        from proctap._native import ProcessLoopback
        self.native = ProcessLoopback(pid)
        try:
            if not self.native.is_process_specific():
                raise RuntimeError('Process-only capture unavailable. Desktop-wide capture is not allowed.')
            format_info = self.native.get_format()
            if (format_info['sample_rate'], format_info['channels'], format_info['bits_per_sample']) != (RATE, CHANNELS, 32):
                raise RuntimeError('This prototype requires 48 kHz stereo float32 process capture.')
        except Exception:
            self.native.stop()
            raise

    def run(self, stop_event, publish, on_level=lambda level: None):
        import numpy as np
        self.native.start()
        pending = bytearray()
        next_frame = time.monotonic()
        next_level = next_frame
        next_process_check = next_frame
        try:
            while not stop_event.is_set():
                if time.monotonic() >= next_process_check:
                    if not self.process.is_running():
                        raise RuntimeError('The selected Pear process exited. Restart sharing after opening Pear again.')
                    next_process_check = time.monotonic() + 0.5
                data = self.native.read()
                if data:
                    samples = np.frombuffer(data, dtype='<f4')
                    samples = np.nan_to_num(samples, nan=0.0, posinf=1.0, neginf=-1.0)
                    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype('<i2').tobytes()
                    pending.extend(pcm)
                    if time.monotonic() >= next_level:
                        on_level(float(np.max(np.abs(samples))) if samples.size else 0.0)
                        next_level = time.monotonic() + 0.25
                # Bound capture delay and pace frames; transmit silence during source gaps.
                if len(pending) > PCM_BYTES * 8:
                    del pending[:-PCM_BYTES * 4]
                now = time.monotonic()
                if now >= next_frame:
                    if len(pending) >= PCM_BYTES:
                        frame = bytes(pending[:PCM_BYTES])
                        del pending[:PCM_BYTES]
                    else:
                        frame = SILENCE
                    publish(frame)
                    next_frame = max(next_frame + 0.02, now)
                stop_event.wait(0.002)
        finally:
            self.native.stop()

    def close(self):
        self.native.stop()


class AudioOutput:
    """One stream, bounded queue, silence on gaps and a local-only gain slider."""
    def __init__(self):
        self.buffer = LiveBuffer()
        self.gain = 0.5
        self.stream = None
        self.received = 0

    def put(self, pcm):
        if len(pcm) != PCM_BYTES:
            raise ValueError('Invalid playback frame.')
        self.received += 1
        self.buffer.put(pcm)

    def start(self):
        import sounddevice as sd
        import numpy as np

        def render(outdata, frames, timing, status):
            frame = self.buffer.get() if frames == FRAMES else None
            if frame is None:
                outdata[:] = bytes(len(outdata))
            else:
                samples = np.frombuffer(frame, dtype='<i2')
                outdata[:] = (samples * self.gain).astype('<i2').tobytes()

        self.stream = sd.RawOutputStream(samplerate=RATE, channels=CHANNELS, dtype='int16',
                                         blocksize=FRAMES, latency='low', callback=render)
        self.stream.start()

    def close(self):
        if self.stream is not None:
            self.stream.abort()
            self.stream.close()
        self.buffer.clear()

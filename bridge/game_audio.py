"""Opus batches and a bounded local file bridge for the game-connection experiment."""
import base64
import math
from pathlib import Path
import re
import secrets
import struct
import time
from urllib.parse import quote, unquote

from audio_stream import FRAMES, PCM_BYTES, RATE
from pear_bridge import BridgeLock

PREFIX = 'AfterdarkGame'
SLOTS = 16
MAX_PAYLOAD = 1000
MAX_SEQUENCE = 2147483647


def write_snapshot(path, fields):
    # Like the game writer, overwrite a fixed file. Readers reject partial writes.
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        for key, value in fields.items():
            stream.write('{}={}\n'.format(key, quote(str(value), safe='')))
        stream.write('commit={}\n'.format(quote(str(fields['serial']), safe='')))


def read_snapshot(path, max_age=2, now=None):
    now = time.time() if now is None else now
    try:
        before = path.stat()
        if not -1 <= now - before.st_mtime <= max_age or before.st_size > 6000:
            return None
        text = path.read_text(encoding='utf-8')
        after = path.stat()
        if before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size:
            return None
        lines = text.splitlines()
        if not lines or len(lines) > 20 or not lines[-1].startswith('commit='):
            return None
        fields = {}
        for line in lines:
            key, value = line.split('=', 1)
            if not re.fullmatch('[a-z_]+', key) or key in fields or len(value) > 3000:
                return None
            fields[key] = unquote(value)
        if fields.get('serial') != fields.get('commit'):
            return None
        return fields
    except (OSError, ValueError, UnicodeError):
        return None


def pack_batch(packets):
    if len(packets) != 2 or any(not 1 <= len(p) <= 360 for p in packets):
        raise ValueError('Expected two bounded 20 ms Opus packets.')
    raw = b'AFG1' + struct.pack('!HH', len(packets[0]), len(packets[1])) + b''.join(packets)
    return base64.b64encode(raw).decode('ascii')


def unpack_batch(payload):
    if not isinstance(payload, str) or not 12 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError('Invalid audio batch size.')
    raw = base64.b64decode(payload, validate=True)
    if len(raw) < 10 or raw[:4] != b'AFG1':
        raise ValueError('Invalid audio batch format.')
    first, second = struct.unpack('!HH', raw[4:8])
    if not 1 <= first <= 360 or not 1 <= second <= 360 or len(raw) != 8 + first + second:
        raise ValueError('Invalid Opus packet sizes.')
    return raw[8:8 + first], raw[8 + first:]


class OpusEncoder:
    def __init__(self):
        import av
        from fractions import Fraction
        self.av = av
        self.time_base = Fraction(1, RATE)
        self.codec = av.CodecContext.create('libopus', 'w')
        self.codec.sample_rate = RATE
        self.codec.layout = 'stereo'
        self.codec.format = 's16'
        self.codec.bit_rate = 64000
        self.codec.time_base = self.time_base
        self.codec.options = {'application': 'audio', 'frame_duration': '20', 'vbr': 'off'}
        self.codec.open()
        self.position = 0
        self.pending = []

    def encode(self, pcm):
        if len(pcm) != PCM_BYTES:
            raise ValueError('Invalid PCM frame size.')
        frame = self.av.AudioFrame(format='s16', layout='stereo', samples=FRAMES)
        frame.sample_rate = RATE
        frame.time_base = self.time_base
        frame.pts = self.position
        frame.planes[0].update(pcm)
        self.position += FRAMES
        self.pending.extend(bytes(packet) for packet in self.codec.encode(frame))
        if len(self.pending) >= 2:
            packets, self.pending = self.pending[:2], self.pending[2:]
            return pack_batch(packets)
        return None


class OpusDecoder:
    def __init__(self):
        import av
        self.av = av
        self.codec = av.CodecContext.create('opus', 'r')
        # A raw Opus stream with a fixed stereo layout; no container or file I/O.
        self.codec.extradata = b'OpusHead' + bytes([1, 2]) + struct.pack('<HIhB', 0, RATE, 0, 0)
        self.codec.open()
        self.resampler = av.AudioResampler(format='s16', layout='stereo', rate=RATE)

    def decode(self, payload):
        frames = []
        for packet in unpack_batch(payload):
            for frame in self.codec.decode(self.av.Packet(packet)):
                if frame.samples != FRAMES or frame.sample_rate != RATE:
                    raise ValueError('Expected a 20 ms Opus frame.')
                for pcm in self.resampler.resample(frame):
                    if pcm.samples != FRAMES:
                        raise ValueError('Unexpected resampled frame size.')
                    frames.append(bytes(pcm.planes[0])[:PCM_BYTES])
        if len(frames) != 2:
            raise ValueError('Incomplete audio batch.')
        return frames


class GameBridge:
    def __init__(self, zomboid_dir, role, clock=time.time):
        if role not in ('listen', 'share', 'tone'):
            raise ValueError('Invalid game audio role.')
        self.folder = Path(zomboid_dir) / 'Lua'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = BridgeLock(self.folder / (PREFIX + '.lock'))
        self.role = role
        self.clock = clock
        self.client = secrets.token_hex(16)
        self.serial = 0
        self.sequence = -1
        self.room = None
        self.encoder = None
        self.decoder = None
        self.rx_room = None
        self.rx_sequence = -1
        self.sent = 0
        self.received = 0
        self.dropped = 0
        self.last_control = -math.inf
        self.state = None
        self.state_deadline = -math.inf

    def heartbeat(self):
        now = self.clock()
        if now - self.last_control >= 0.2:
            self.last_control = now
            self.serial += 1
            write_snapshot(self.folder / (PREFIX + '.control.txt'), dict(
                serial=self.serial, client=self.client, role=self.role, timestamp=int(now * 1000)))
        path = self.folder / (PREFIX + '.status.txt')
        state = read_snapshot(path, max_age=0.8, now=now)
        if state and state.get('client') == self.client:
            try:
                self.state_deadline = min(now + 0.4, path.stat().st_mtime + 0.8)
                self.state = state
            except OSError:
                pass
        if now > self.state_deadline:
            self.state = None
        return self.state

    def publish(self, pcm):
        state = self.heartbeat()
        room = state.get('room') if state and state.get('status') == 'sending' else None
        if not room:
            self.pause_source()
            return
        if self.room != room:
            self.room = room
            self.sequence = -1
            self.encoder = None
        if self.encoder is None:
            self.encoder = OpusEncoder()
        payload = self.encoder.encode(pcm)
        if payload is None:
            return
        self.sequence += 1
        if self.sequence > MAX_SEQUENCE:
            raise RuntimeError('Restart the game audio session to reset its sequence.')
        fields = dict(serial=self.sequence, client=self.client, room=room, payload=payload,
                      timestamp=int(self.clock() * 1000))
        write_snapshot(self.folder / '{}.tx.{}.txt'.format(PREFIX, self.sequence % SLOTS), fields)
        write_snapshot(self.folder / (PREFIX + '.tx.txt'), dict(
            serial=self.sequence, client=self.client, room=room, timestamp=fields['timestamp']))
        self.sent += 1

    def pause_source(self):
        # A partial status snapshot must never restart sequence numbers in the same room.
        if self.encoder is not None:
            self.encoder = None
            self.sequence += 1  # Signal a decoder reset when this room resumes.

    def receive(self):
        state = self.heartbeat()
        if not state or state.get('status') != 'listening' or not state.get('room'):
            self.decoder = None
            return []
        room = state['room']
        if room != self.rx_room:
            self.rx_room = room
            self.rx_sequence = -1
            self.decoder = None
        manifest = read_snapshot(self.folder / (PREFIX + '.rx.txt'), max_age=0.4, now=self.clock())
        if not manifest or manifest.get('client') != self.client or manifest.get('room') != room:
            return []
        try:
            latest = int(manifest['serial'])
            if not 0 <= latest <= MAX_SEQUENCE:
                return []
        except (KeyError, ValueError):
            return []
        start = max(self.rx_sequence + 1, latest - 3)
        result = []
        from av.error import FFmpegError
        for sequence in range(start, latest + 1):
            snapshot = read_snapshot(self.folder / '{}.rx.{}.txt'.format(PREFIX, sequence % SLOTS), max_age=0.4, now=self.clock())
            if not snapshot or snapshot.get('client') != self.client or snapshot.get('room') != room or snapshot.get('serial') != str(sequence):
                continue
            if sequence != self.rx_sequence + 1:
                if self.rx_sequence >= 0:
                    self.dropped += max(0, sequence - self.rx_sequence - 1)
                self.decoder = None
            self.rx_sequence = sequence
            try:
                if self.decoder is None:
                    self.decoder = OpusDecoder()
                result.extend(self.decoder.decode(snapshot.get('payload', '')))
                self.received += 1
            except (ValueError, FFmpegError):
                self.dropped += 1
                self.decoder = None
        return result

    def close(self):
        try:
            self.serial += 1
            write_snapshot(self.folder / (PREFIX + '.control.txt'), dict(
                serial=self.serial, client=self.client, role='stop', timestamp=int(self.clock() * 1000)))
        finally:
            self.lock.close()

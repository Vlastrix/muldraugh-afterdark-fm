"""Experimental LAN audio transport. Independent of Pear APIs and game commands."""
import base64
from collections import deque
import hashlib
import json
import secrets
import socket
import ssl
import struct
import tempfile
import threading
import time
from pathlib import Path
import zlib

RATE = 48000
CHANNELS = 2
FRAMES = 960  # 20 milliseconds
PCM_BYTES = FRAMES * CHANNELS * 2
MAX_PACKET = 8192
HEADER = struct.Struct('!4sQI')
MAGIC = b'AFS1'
PREFIX = 'afterdark://'
SILENCE = bytes(PCM_BYTES)


def make_invite(host, port, token, fingerprint):
    data = dict(version=1, host=host, port=port, token=token, fingerprint=fingerprint)
    return PREFIX + base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')


def parse_invite(invite):
    if not invite.startswith(PREFIX) or len(invite) > 2048:
        raise ValueError('Paste an Afterdark invitation from the sender.')
    try:
        encoded = invite[len(PREFIX):]
        data = json.loads(base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True))
        valid = (type(data['version']) is int and data['version'] == 1 and isinstance(data['host'], str)
                 and 0 < len(data['host']) <= 253 and not any(c.isspace() for c in data['host'])
                 and type(data['port']) is int and 1 <= data['port'] <= 65535
                 and isinstance(data['token'], str) and 24 <= len(data['token']) <= 128
                 and all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in data['token'])
                 and isinstance(data['fingerprint'], str) and len(data['fingerprint']) == 64
                 and all(c in '0123456789abcdef' for c in data['fingerprint']))
        if not valid:
            raise ValueError()
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise ValueError('Invalid Afterdark invitation.') from None
    return data


def recv_exact(connection, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise EOFError('Audio connection closed.')
        chunks.extend(chunk)
    return bytes(chunks)


def encode_frame(sequence, pcm):
    if len(pcm) != PCM_BYTES:
        raise ValueError('Unexpected PCM frame size.')
    compressed = zlib.compress(pcm, 1)
    return HEADER.pack(MAGIC, sequence, len(compressed)) + compressed


def receive_frame(connection):
    magic, sequence, size = HEADER.unpack(recv_exact(connection, HEADER.size))
    if magic != MAGIC or not 1 <= size <= MAX_PACKET:
        raise ValueError('Invalid audio frame header.')
    decoder = zlib.decompressobj()
    pcm = decoder.decompress(recv_exact(connection, size), PCM_BYTES + 1)
    if len(pcm) != PCM_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('Invalid compressed audio frame.')
    return sequence, pcm


class LiveBuffer:
    """Drop old audio instead of building an ever-growing playback delay."""
    def __init__(self, capacity=8, max_age=0.2, clock=time.monotonic):
        self.items = deque(maxlen=capacity)
        self.max_age = max_age
        self.clock = clock
        self.lock = threading.Lock()
        self.dropped = 0

    def put(self, value):
        with self.lock:
            if len(self.items) == self.items.maxlen:
                self.dropped += 1
            self.items.append((self.clock(), value))

    def get(self):
        with self.lock:
            while self.items:
                timestamp, value = self.items.popleft()
                if self.clock() - timestamp <= self.max_age:
                    return value
                self.dropped += 1
        return None

    def clear(self):
        with self.lock:
            self.items.clear()


def create_identity(folder):
    """Ephemeral TLS identity pinned by the invitation; no stored account secrets."""
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Afterdark FM Connector')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=1))
                   .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
    cert_path, key_path = Path(folder) / 'cert.pem', Path(folder) / 'key.pem'
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_path, key_path)
    return context, certificate.fingerprint(hashes.SHA256()).hex()


class AudioHost:
    """Small direct TLS broadcaster. Capture never waits for slow listeners."""
    def __init__(self, on_status=lambda message: None):
        self.on_status = on_status
        self.stop_event = threading.Event()
        self.clients = {}
        self.pending = set()
        self.workers = []
        self.lock = threading.Lock()
        self.listener = None
        self.sequence = 0
        self.token = secrets.token_urlsafe(32)
        self.invite = None

    def start(self, advertised_host, port=26539, bind_host='0.0.0.0'):
        with tempfile.TemporaryDirectory(prefix='afterdark-tls-') as folder:
            self.context, fingerprint = create_identity(folder)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind((bind_host, port))
            listener.listen(8)
            listener.settimeout(0.2)
        except Exception:
            listener.close()
            raise
        self.listener = listener
        self.invite = make_invite(advertised_host, listener.getsockname()[1], self.token, fingerprint)
        self._spawn(self._accept)
        return self.invite

    def _spawn(self, target, *args):
        worker = threading.Thread(target=target, args=args, daemon=True)
        with self.lock:
            self.workers = [w for w in self.workers if w.is_alive()]
            self.workers.append(worker)
        worker.start()

    def _accept(self):
        while not self.stop_event.is_set():
            try:
                raw, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self.lock:
                full = len(self.pending) + len(self.clients) >= 8
                if not full:
                    self.pending.add(raw)
            if full:
                raw.close()
            else:
                self._spawn(self._serve, raw)

    def _serve(self, raw):
        connection = raw
        try:
            raw.settimeout(2)
            connection = self.context.wrap_socket(raw, server_side=True)
            with self.lock:
                self.pending.discard(raw)
                self.pending.add(connection)
            size = struct.unpack('!H', recv_exact(connection, 2))[0]
            if not 1 <= size <= 128:
                raise ValueError('Invalid authentication request.')
            supplied = recv_exact(connection, size)
            if not secrets.compare_digest(supplied, self.token.encode('ascii')):
                raise ValueError('Invitation rejected.')
            connection.sendall(MAGIC)
            buffer = LiveBuffer()
            with self.lock:
                self.pending.discard(connection)
                self.clients[connection] = buffer
                count = len(self.clients)
            self.on_status('Listeners connected: {}'.format(count))
            while not self.stop_event.is_set():
                packet = buffer.get()
                if packet is None:
                    self.stop_event.wait(0.005)
                    continue
                connection.sendall(packet)
        except (OSError, EOFError, ValueError):
            pass
        finally:
            with self.lock:
                self.pending.discard(raw)
                self.pending.discard(connection)
                was_client = self.clients.pop(connection, None) is not None
                count = len(self.clients)
            connection.close()
            if was_client:
                self.on_status('Listeners connected: {}'.format(count))

    def publish(self, pcm):
        packet = encode_frame(self.sequence, pcm)
        self.sequence += 1
        with self.lock:
            buffers = list(self.clients.values())
        for buffer in buffers:
            buffer.put(packet)

    def close(self):
        self.stop_event.set()
        if self.listener:
            self.listener.close()
        with self.lock:
            sockets = list(self.clients) + list(self.pending)
            workers = list(self.workers)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=2.5)


def receive_audio(invite, stop_event, on_frame, on_status=lambda message: None):
    settings = parse_invite(invite)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    # Trust the exact certificate in the invitation instead of a public CA.
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((settings['host'], settings['port']), timeout=3) as raw:
            with context.wrap_socket(raw, server_hostname=settings['host']) as connection:
                fingerprint = hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest()
                if not secrets.compare_digest(fingerprint, settings['fingerprint']):
                    raise ValueError('Sender certificate does not match the invitation.')
                token = settings['token'].encode('ascii')
                connection.sendall(struct.pack('!H', len(token)) + token)
                if recv_exact(connection, len(MAGIC)) != MAGIC:
                    raise ValueError('Sender rejected the invitation.')
                connection.settimeout(0.5)
                on_status('Connected. Receiving Pear audio; Pear is not required on this computer.')
                previous = -1
                while not stop_event.is_set():
                    # A timeout during a partial frame invalidates this connection.
                    # Do not restart parsing in the middle of a frame.
                    sequence, pcm = receive_frame(connection)
                    if sequence <= previous:
                        raise ValueError('Out-of-order audio frame.')
                    previous = sequence
                    on_frame(pcm)
    finally:
        on_status('Audio connection stopped.')

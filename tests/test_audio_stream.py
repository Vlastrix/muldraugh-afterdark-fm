"""Audio transport checks use real local TLS sockets, not a game or Pear session."""
import base64
import importlib.util
import json
from pathlib import Path
import socket
import struct
import sys
import threading
import time
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from audio_stream import (AudioHost, HEADER, LiveBuffer, MAGIC, PCM_BYTES, SILENCE,
                          encode_frame, make_invite, parse_invite, receive_audio, receive_frame)


class ProtocolTests(unittest.TestCase):
    def test_frame_survives_fragmented_socket_reads(self):
        pcm = bytes(range(256)) * (PCM_BYTES // 256)
        packet = encode_frame(51, pcm)

        class Fragmented:
            def recv(self, size):
                nonlocal packet
                result, packet = packet[:min(size, 7)], packet[min(size, 7):]
                return result

        self.assertEqual(receive_frame(Fragmented()), (51, pcm))

    def test_rejects_truncated_oversize_and_decompression_bomb(self):
        cases = [b'AF', HEADER.pack(b'BAD!', 0, 1), HEADER.pack(MAGIC, 0, 90000),
                 HEADER.pack(MAGIC, 0, 10) + b'brokenfile',
                 HEADER.pack(MAGIC, 0, len(zlib.compress(bytes(PCM_BYTES * 100)))) + zlib.compress(bytes(PCM_BYTES * 100))]
        for packet in cases:
            with self.subTest(size=len(packet)):
                class Source:
                    def recv(self, size):
                        nonlocal packet
                        result, packet = packet[:size], packet[size:]
                        return result
                with self.assertRaises((ValueError, EOFError, zlib.error)):
                    receive_frame(Source())

    def test_invalid_invitation_does_not_open_network_connection(self):
        with patch('audio_stream.socket.create_connection') as connect:
            with self.assertRaises(ValueError):
                receive_audio('not an invitation', threading.Event(), lambda frame: None)
            connect.assert_not_called()

    def test_invitation_validates_fields(self):
        invite = make_invite('127.0.0.1', 26539, 'a' * 32, 'b' * 64)
        self.assertEqual(parse_invite(invite)['port'], 26539)
        settings = parse_invite(invite)
        for key, value in [('port', True), ('version', True), ('host', ''), ('fingerprint', 'z' * 64), ('token', 'secret!')]:
            invalid = dict(settings, **{key: value})
            encoded = base64.urlsafe_b64encode(json.dumps(invalid).encode()).decode()
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_invite('afterdark://' + encoded)

    def test_live_buffer_drops_old_and_expired_audio(self):
        now = [1.0]
        buffer = LiveBuffer(capacity=2, clock=lambda: now[0])
        buffer.put(b'oldest')
        buffer.put(b'older')
        buffer.put(b'latest')
        self.assertEqual(buffer.get(), b'older')
        now[0] += 0.3
        self.assertIsNone(buffer.get())
        self.assertEqual(buffer.dropped, 2)
        buffer.put(b'new session')
        buffer.clear()
        self.assertIsNone(buffer.get())


@unittest.skipUnless(importlib.util.find_spec('cryptography'), 'Install streaming dependencies for TLS integration tests')
class TransportTests(unittest.TestCase):
    def setUp(self):
        self.host = AudioHost()
        self.invite = self.host.start('127.0.0.1', port=0, bind_host='127.0.0.1')
        self.stop = threading.Event()
        self.received = threading.Event()
        self.errors = []
        self.frames = []
        self.receiver = None

    def tearDown(self):
        self.stop.set()
        self.host.close()
        if self.receiver:
            self.receiver.join(4)
            self.assertFalse(self.receiver.is_alive(), 'Receiver did not shut down')

    def listen(self, invite=None):
        def frame(pcm):
            self.frames.append(pcm)
            self.received.set()

        def work():
            try:
                receive_audio(invite or self.invite, self.stop, frame)
            except (OSError, EOFError, ValueError) as error:
                self.errors.append(error)
        self.receiver = threading.Thread(target=work, daemon=True)
        self.receiver.start()

    def test_real_tls_stream_transfers_audio_without_pear(self):
        self.listen()
        until = time.monotonic() + 4
        while not self.received.is_set() and time.monotonic() < until:
            self.host.publish(SILENCE)
            time.sleep(0.02)
        self.assertTrue(self.received.is_set())
        self.assertEqual(self.frames[0], SILENCE)
        self.assertEqual(self.errors, [])

    def test_wrong_session_key_cannot_receive_audio(self):
        settings = parse_invite(self.invite)
        self.listen(make_invite(settings['host'], settings['port'], 'x' * 32, settings['fingerprint']))
        self.receiver.join(4)
        self.assertFalse(self.receiver.is_alive())
        self.assertFalse(self.frames)
        self.assertTrue(self.errors)
        self.assertFalse(self.host.clients)

    def test_wrong_certificate_fingerprint_is_rejected(self):
        settings = parse_invite(self.invite)
        self.listen(make_invite(settings['host'], settings['port'], settings['token'], '0' * 64))
        self.receiver.join(4)
        self.assertFalse(self.frames)
        self.assertTrue(any('certificate' in str(error) for error in self.errors))

    def test_host_shutdown_disconnects_receiver_and_releases_port(self):
        self.listen()
        until = time.monotonic() + 4
        while not self.received.is_set() and time.monotonic() < until:
            self.host.publish(SILENCE)
            time.sleep(0.02)
        self.assertTrue(self.received.is_set())
        port = self.host.listener.getsockname()[1]
        self.host.close()
        self.receiver.join(4)
        self.assertFalse(self.receiver.is_alive())
        with socket.socket() as replacement:
            replacement.bind(('127.0.0.1', port))


@unittest.skipUnless(sys.platform == 'win32', 'Windows process capture guard')
class CaptureIsolationTests(unittest.TestCase):
    def test_desktop_capture_fallback_is_rejected_and_stopped(self):
        from audio_devices import PearCapture
        from types import SimpleNamespace
        from unittest.mock import Mock
        native = Mock()
        native.is_process_specific.return_value = False
        modules = {'psutil': SimpleNamespace(Process=lambda pid: object()),
                   'proctap': SimpleNamespace(),
                   'proctap._native': SimpleNamespace(ProcessLoopback=lambda pid: native)}
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(RuntimeError, 'Desktop-wide capture is not allowed'):
                PearCapture(123)
        native.stop.assert_called_once()

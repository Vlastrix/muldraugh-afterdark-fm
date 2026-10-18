"""Game Lua runs against a queued network harness; this is not a live server test."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from game_audio import GameBridge, OpusDecoder, OpusEncoder, pack_batch, read_snapshot, unpack_batch, write_snapshot
from audio_stream import PCM_BYTES
from test_lua import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
LUA = ROOT / 'mod/PearCarRadio/common/media/lua'

HARNESS = '''
callbacks = {}
Events = setmetatable({}, {__index=function(t,name)
 local handlers={}
 local event={Add=function(fn) table.insert(handlers,fn) end,
  emit=function(...) for _,fn in ipairs(handlers) do fn(...) end end}
 rawset(t,name,event); return event
end})
function require(name) end
function getTimestampMs() return now end
function isServer() return server end
function isClient() return not server end
function player(id)
 return {getOnlineID=function() return id end,getUsername=function() return 'Player'..id end}
end
function getOnlinePlayers()
 return {size=function() return 3 end,get=function(self,i) return player(i) end}
end
'''

RADIO_WORLD = '''
function list(values)
 return {size=function() return #values end,get=function(self,i) return values[i+1] end}
end
function data()
 return {channel=94600,on=true,power=true,volume=1,
  getChannel=function(self) return self.channel end,
  getIsTurnedOn=function(self) return self.on end,
  canBePoweredHere=function(self) return self.power end,
  getDeviceVolume=function(self) return self.volume end,
  getIsTelevision=function() return false end,
  doReceiveSignal=function() end,getEmitter=function() return nil end,cleanSoundsAndEmitter=function() end}
end
car={id=7,x=20,y=20,z=0}
square={}
car.getId=function(self) return self.id end
car.getX=function(self) return self.x end
car.getY=function(self) return self.y end
car.getZ=function(self) return self.z end
car.getSquare=function() return square end
part={kind='VehiclePart',data=data()}
part.getDeviceData=function(self) return self.data end
part.getVehicle=function() return car end
part.getInventoryItem=function() return {} end
part.getX=car.getX; part.getY=car.getY; part.getZ=car.getZ
part.x=20;part.y=20;part.z=0
car.getPartById=function(self,id) if id=='Radio' then return part end end
world={kind='IsoWaveSignal',x=20,y=20,z=0,data=data()}
world.getDeviceData=part.getDeviceData
world.getX=car.getX;world.getY=car.getY;world.getZ=car.getZ
world.getSquare=function() return square end
world.getObjectIndex=function() return 0 end
objects={world}
square.getObjects=function() return list(objects) end
function getCell() return {getGridSquare=function(self,x,y,z) if x==20 and y==20 and z==0 then return square end end} end
function getVehicleById(id) if id==7 then return car end end
function instanceof(object,kind) return object and object.kind==kind end
names={}
function getZomboidRadio() return {getChannelName=function(self,f) return names[f] end,
 addChannelName=function(self,name,f) names[f]=name end} end
players={}
for id=0,2 do
 local p={id=id,x=20,y=20,z=0,dead=false,vehicle=car}
 p.getOnlineID=function(self) return self.id end
 p.getUsername=function(self) return 'Player'..self.id end
 p.getX=car.getX;p.getY=car.getY;p.getZ=car.getZ
 p.getVehicle=function(self) return self.vehicle end
 p.isDead=function(self) return self.dead end
 players[id]=p
end
function player(id) return players[id] end
noise={}
function addSound(source,x,y,z,radius,volume) table.insert(noise,{x=x,y=y,radius=radius}) end
'''


class Realm:
    def __init__(self, network, player_id=None):
        self.network = network
        self.player_id = player_id
        self.folder = Path(network.temporary.name) / ('server' if player_id is None else str(player_id))
        (self.folder / 'Lua').mkdir(parents=True)
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        globals_ = self.lua.globals()
        globals_.server = player_id is None
        globals_.now = network.now
        self.lua.execute(HARNESS)
        if network.radio:
            self.lua.execute(RADIO_WORLD)
        globals_.getFileReader = self.reader
        globals_.getFileWriter = self.writer

        def client_send(module, command, args):
            network.queue.append(('client', player_id, module, command, copy_table(args)))

        def server_send(player, module, command, args):
            network.queue.append(('server', player.getOnlineID(player), module, command, copy_table(args)))

        globals_.sendClientCommand = client_send
        globals_.sendServerCommand = server_send
        self.lua.execute((LUA / 'shared/AfterdarkGameProtocol.lua').read_text())
        if network.radio:
            self.lua.execute((LUA / 'shared/AfterdarkRadioDevices.lua').read_text())
            self.lua.execute((LUA / ('server/AfterdarkRadioServer.lua' if player_id is None else 'client/AfterdarkRadioClient.lua')).read_text())
        self.lua.execute((LUA / ('server/AfterdarkGameServer.lua' if player_id is None else 'client/AfterdarkGameClient.lua')).read_text())

    def reader(self, name, create):
        file = self.folder / 'Lua' / name
        if not file.exists():
            return None
        lines = iter(file.read_text(encoding='utf-8').splitlines())
        return self.lua.table_from({'readLine': lambda self: next(lines, None), 'close': lambda self: None})

    def writer(self, name, create, append):
        parts = []
        folder = self.folder
        network = self.network
        def close(file):
            path = folder / 'Lua' / name
            path.write_text(''.join(parts), encoding='utf-8')
            os.utime(path, (network.now / 1000, network.now / 1000))
        return self.lua.table_from({'write': lambda self, value: parts.append(value),
                                    'close': close})

    def tick(self):
        self.lua.globals().now = self.network.now
        self.lua.globals().Events.OnTick.emit()


def copy_table(table):
    return {key: copy_table(value) if hasattr(value, 'items') else value for key, value in table.items()}


class Network:
    def __init__(self, radio=False):
        self.radio = radio
        self.now = int(time.time() * 1000)
        self.temporary = tempfile.TemporaryDirectory()
        self.queue = []
        self.delivered = []
        self.server = Realm(self)
        self.clients = {i: Realm(self, i) for i in range(3)}

    def flush(self):
        while self.queue:
            direction, player_id, module, command, args = self.queue.pop(0)
            self.delivered.append((direction, player_id, command, args))
            realm = self.server if direction == 'client' else self.clients[player_id]
            realm.lua.globals().now = self.now
            args = realm.lua.table_from(args, recursive=True)
            if direction == 'client':
                realm.lua.globals().Events.OnClientCommand.emit(module, command, realm.lua.globals().player(player_id), args)
            else:
                realm.lua.globals().Events.OnServerCommand.emit(module, command, args)

    def command(self, player_id, command, args):
        self.queue.append(('client', player_id, 'AfterdarkGameLab', command, args))
        self.flush()

    def tick(self, milliseconds=0):
        self.now += milliseconds
        for realm in self.clients.values():
            realm.tick()
        self.flush()
        self.server.tick()
        self.flush()


class SnapshotTests(unittest.TestCase):
    def test_partial_duplicate_and_stale_snapshots_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.txt'
            for text in ['serial=1\n', 'serial=1\nserial=1\ncommit=1\n', 'serial=1\ncommit=2\n']:
                path.write_text(text)
                self.assertIsNone(read_snapshot(path))
            write_snapshot(path, dict(serial=3, payload='a+/='))
            self.assertEqual(read_snapshot(path)['payload'], 'a+/=')
            self.assertIsNone(read_snapshot(path, now=path.stat().st_mtime + 3))

    def test_batch_rejects_invalid_framing_and_oversize_data(self):
        payload = pack_batch([b'one', b'two'])
        self.assertEqual(unpack_batch(payload), (b'one', b'two'))
        for invalid in ['a' * 1004, 'not base64!!', 'QUZHMQAAAAA=']:
            with self.assertRaises(ValueError):
                unpack_batch(invalid)

    def test_only_one_connector_can_use_a_game_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = GameBridge(folder, 'listen')
            try:
                with self.assertRaises(OSError):
                    GameBridge(folder, 'listen')
            finally:
                bridge.close()
            replacement = GameBridge(folder, 'listen')
            replacement.close()


@unittest.skipUnless(LuaRuntime, 'Optional Lua 5.1 harness requires lupa')
class GameNetworkTests(unittest.TestCase):
    def setUp(self):
        self.network = Network()
        self.addCleanup(self.network.temporary.cleanup)
        self.keys = {i: str(i + 1) * 32 for i in range(3)}
        self.payload = pack_batch([b'one', b'two'])

    def hello(self, player_id, role):
        self.network.command(player_id, 'hello', dict(client=self.keys[player_id], role=role, echo=self.network.now))

    def session(self):
        return next(args['room'] for direction, player_id, command, args in reversed(self.network.delivered)
                    if direction == 'server' and player_id == 0 and command == 'state' and args['status'] == 'sending')

    def audio(self, player_id=0, sequence=0, **changes):
        args = dict(client=self.keys[player_id], room=self.session(), sequence=sequence, payload=self.payload)
        args.update(changes)
        self.network.command(player_id, 'audio', args)

    def audio_deliveries(self):
        return [message for message in self.network.delivered if message[0] == 'server' and message[2] == 'audio']

    def test_no_connector_signal_means_no_network_activity(self):
        self.network.tick()
        self.assertEqual(self.network.delivered, [])

    def write_control(self, role='tone'):
        path = self.network.clients[0].folder / 'Lua/AfterdarkGame.control.txt'
        write_snapshot(path, dict(serial=1, client=self.keys[0], role=role, timestamp=self.network.now))
        return path

    def test_partial_control_write_preserves_room_until_original_heartbeat_expires(self):
        path = self.write_control()
        self.network.tick()
        room = self.session()
        path.write_text('serial=2\n')
        for _ in range(9):
            self.network.tick(200)
        self.assertFalse(any(command == 'leave' for _, _, command, _ in self.network.delivered))
        self.write_control()
        self.network.tick(200)
        self.assertEqual(self.session(), room)
        path.write_text('serial=3\n')
        for _ in range(11):
            self.network.tick(200)
        leaves = [message for message in self.network.delivered if message[2] == 'leave']
        self.assertEqual(len(leaves), 1)

    def test_valid_stop_control_leaves_immediately(self):
        self.write_control()
        self.network.tick()
        self.write_control('stop')
        self.network.tick(40)
        self.assertTrue(any(command == 'leave' for _, _, command, _ in self.network.delivered))

    def test_over_twelve_hundred_batches_keep_counters_and_room_during_partial_reads(self):
        path = self.write_control()
        self.network.tick()
        room = self.session()
        folder = path.parent
        for sequence in range(1305):
            self.write_control()
            if sequence % 41 == 0:
                path.write_text('serial=unfinished\n')
            packet = dict(serial=sequence, client=self.keys[0], room=room,
                          timestamp=self.network.now, payload=self.payload)
            write_snapshot(folder / f'AfterdarkGame.tx.{sequence % 16}.txt', packet)
            write_snapshot(folder / 'AfterdarkGame.tx.txt', packet)
            self.network.tick(40)
        self.write_control()
        self.network.tick(200)
        state = read_snapshot(folder / 'AfterdarkGame.status.txt', now=self.network.now / 1000)
        self.assertEqual(state['sent'], '1305')
        self.assertEqual(state['confirmed'], '1305')
        self.assertEqual(state['room_changes'], '0')
        self.assertEqual(state['room'], room)
        self.assertFalse(any(command == 'leave' for _, _, command, _ in self.network.delivered))
        # A genuine room restart remains visible without erasing this run's totals.
        self.write_control('stop')
        self.network.tick(40)
        self.write_control()
        self.network.tick(600)
        self.network.tick(200)
        state = read_snapshot(folder / 'AfterdarkGame.status.txt', now=self.network.now / 1000)
        self.assertEqual(state['sent'], '1305')
        self.assertEqual(state['confirmed'], '1305')
        self.assertEqual(state['room_changes'], '1')
        self.assertNotEqual(state['room'], room)

    def test_server_relays_only_to_explicit_listeners_and_keeps_source_identity(self):
        self.hello(1, 'listen')
        self.hello(0, 'tone')
        self.audio()
        deliveries = self.audio_deliveries()
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0][1], 1)
        self.assertEqual(deliveries[0][3]['client'], self.keys[1])
        self.assertRegex(deliveries[0][3]['room'], r'^\d{13}_\d+$')

    def test_listener_cannot_impersonate_owner_even_with_owner_token(self):
        self.hello(1, 'listen')
        self.hello(0, 'share')
        self.audio(player_id=1, client=self.keys[0])
        self.assertFalse(self.audio_deliveries())

    def test_bad_payload_duplicate_sequence_and_wrong_room_are_not_forwarded(self):
        self.hello(1, 'listen')
        self.hello(0, 'tone')
        self.audio(payload='a' * 1004)
        self.audio(room='old_session')
        self.audio(sequence=float('nan'))
        self.audio(sequence=0)
        self.audio(sequence=0)
        self.assertEqual(len(self.audio_deliveries()), 1)

    def test_server_caps_sender_at_thirty_batches_per_window(self):
        self.hello(1, 'listen')
        self.hello(0, 'tone')
        for sequence in range(35):
            self.audio(sequence=sequence)
        self.assertEqual(len(self.audio_deliveries()), 30)

    def test_owner_leave_invalidates_old_room_before_new_owner(self):
        self.hello(1, 'listen')
        self.hello(0, 'tone')
        old_room = self.session()
        self.network.command(0, 'leave', dict(client=self.keys[0]))
        self.hello(2, 'share')
        self.network.command(0, 'audio', dict(client=self.keys[0], room=old_room, sequence=1, payload=self.payload))
        self.assertFalse(self.audio_deliveries())
        latest = [args for direction, player_id, command, args in self.network.delivered if direction == 'server' and player_id == 1 and command == 'state'][-1]
        self.assertNotEqual(latest['room'], old_room)

    def test_owner_timeout_clears_listener_session(self):
        self.hello(1, 'listen')
        self.hello(0, 'tone')
        self.network.now += 3100
        self.hello(1, 'listen')
        self.network.server.tick()
        self.network.flush()
        state = [args for direction, player_id, command, args in self.network.delivered if direction == 'server' and player_id == 1 and command == 'state'][-1]
        self.assertEqual(state['status'], 'waiting')
        self.assertEqual(state['room'], '')

    @unittest.skipUnless(importlib.util.find_spec('av'), 'Streaming build needs PyAV for the real codec test')
    def test_real_opus_crosses_connector_files_and_lua_server_relay(self):
        source = GameBridge(self.network.clients[0].folder, 'tone', clock=lambda: self.network.now / 1000)
        listener = GameBridge(self.network.clients[1].folder, 'listen', clock=lambda: self.network.now / 1000)
        self.addCleanup(source.close)
        self.addCleanup(listener.close)
        self.keys[0], self.keys[1] = source.client, listener.client
        source.heartbeat()
        listener.heartbeat()
        self.network.tick()
        self.network.tick(210)
        source.publish(bytes(PCM_BYTES))
        source.publish(bytes(PCM_BYTES))
        self.network.tick(40)
        received = listener.receive()
        self.assertEqual(len(received), 2)
        self.assertEqual([len(frame) for frame in received], [PCM_BYTES, PCM_BYTES])
        self.assertEqual(source.sent, 1)
        self.assertEqual(listener.received, 1)
        self.assertEqual(listener.receive(), [])
        self.network.tick(210)
        self.assertEqual(source.heartbeat()['confirmed'], '1')
        # Simulate reading status while Lua is rewriting it. Do not replay an old batch
        # or reset the source sequence within a server session.
        (source.folder / 'AfterdarkGame.status.txt').write_text('serial=broken\n')
        (listener.folder / 'AfterdarkGame.status.txt').write_text('serial=broken\n')
        source.publish(bytes(PCM_BYTES))
        self.assertEqual(listener.receive(), [])
        self.network.tick(210)
        self.assertEqual(listener.receive(), [])
        source.publish(bytes(PCM_BYTES))
        source.publish(bytes(PCM_BYTES))
        self.network.tick(40)
        self.assertEqual(len(listener.receive()), 2)
        self.assertEqual(source.sent, 2)
        self.assertEqual(listener.received, 2)
        # A prolonged missing signal expires the cache, but resuming the same room
        # still advances its sequence instead of replaying numbers rejected by the server.
        (source.folder / 'AfterdarkGame.status.txt').write_text('serial=broken\n')
        (listener.folder / 'AfterdarkGame.status.txt').write_text('serial=broken\n')
        self.network.now += 1000
        source.publish(bytes(PCM_BYTES))
        self.assertEqual(listener.receive(), [])
        self.network.tick(210)
        source.publish(bytes(PCM_BYTES))
        source.publish(bytes(PCM_BYTES))
        self.network.tick(40)
        self.assertEqual(len(listener.receive()), 2)
        self.assertEqual(source.sent, 3)
        self.assertEqual(listener.received, 3)


@unittest.skipUnless(importlib.util.find_spec('av'), 'Streaming build needs PyAV')
class CodecTests(unittest.TestCase):
    def test_real_opus_is_bounded_and_decodes_to_fixed_pcm_frames(self):
        encoder, decoder = OpusEncoder(), OpusDecoder()
        import math, struct
        pcm = b''.join(struct.pack('<hh', int(2000 * math.sin(i / 10)), int(2000 * math.sin(i / 10))) for i in range(960))
        self.assertIsNone(encoder.encode(pcm))
        payload = encoder.encode(pcm)
        self.assertLess(len(payload), 1000)
        frames = decoder.decode(payload)
        self.assertEqual([len(frame) for frame in frames], [PCM_BYTES, PCM_BYTES])
        self.assertNotEqual(frames[1], bytes(PCM_BYTES))

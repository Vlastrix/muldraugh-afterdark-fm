"""Radio authority and local Pear control checks; game behavior still needs live testing."""
import importlib.util
import unittest
import threading
import time
from unittest.mock import patch

from test_game_audio import Network, LuaRuntime, LUA, pack_batch, write_snapshot
from game_audio import GameBridge
from audio_stream import PCM_BYTES
from radio_audio import PearRadioControl


class FakePear:
    def __init__(self):
        self.actions = []
        self.fail_next = False
        self.volumes = []

    def post(self, action, data=None):
        if action == 'volume':
            self.volumes.append(data['volume'])
            return
        self.actions.append(action)
        if self.fail_next and action == 'next':
            self.fail_next = False
            raise OSError('Lost HTTP response')

    def get(self, endpoint):
        if endpoint == 'volume':
            return dict(state=65)
        return dict(videoId='track', isPaused=False, title='Song', artist='Artist')


class PearRadioTests(unittest.TestCase):
    def test_listener_never_controls_local_pear_and_owner_release_pauses_once(self):
        api = FakePear()
        controller = PearRadioControl(api)
        controller.step(None)
        self.assertEqual(api.actions, [])
        state = dict(owning='1', room='one', paused='0', volume='100')
        report = controller.step(state)
        controller.step(state)
        self.assertEqual(report['playing'], '1')
        controller.step(None)
        controller.step(None)
        self.assertEqual(api.actions, ['play', 'pause'])
        self.assertEqual(api.volumes, [100, 65])

    def test_commands_are_consumed_once_even_when_http_response_is_lost(self):
        api = FakePear()
        controller = PearRadioControl(api)
        state = dict(owning='1', room='one', paused='0', volume='100', command_id='1', action='next')
        api.fail_next = True
        with self.assertRaises(OSError):
            controller.step(state)
        controller.step(state)
        self.assertEqual(api.actions, ['play', 'next'])
        state.update(room='two')
        controller.step(state)
        self.assertEqual(api.actions, ['play', 'next', 'play', 'next'])

    def test_shared_volume_changes_include_zero_and_restore_original_on_release(self):
        api=FakePear()
        control=PearRadioControl(api)
        state=dict(owning='1',room='radio',paused='0',volume='40')
        control.step(state)
        control.step(state)
        state['volume']='0'
        control.step(state)
        control.step(None)
        self.assertEqual(api.volumes,[40,0,65])


@unittest.skipUnless(LuaRuntime and importlib.util.find_spec('av'), 'Worker integration needs Lua and PyAV')
class RadioWorkerTests(unittest.TestCase):
    def test_two_workers_stream_through_lua_and_apply_passenger_pause_without_listener_pear(self):
        from audio_stream import LiveBuffer
        from radio_audio import run_radio
        network=Network(radio=True)
        stop=threading.Event()
        outputs, failures, apis = {}, [], []

        class API(FakePear):
            def __init__(self):
                super().__init__()
                self.token=None
                apis.append(self)
            def connect(self):
                self.token='test-token'

        class Capture:
            def __init__(self,*args):
                pass
            def run(self,stop,publish):
                while not stop.is_set():
                    publish(bytes(PCM_BYTES))
                    stop.wait(0.02)
            def close(self):
                pass

        class Output:
            def __init__(self):
                self.buffer=LiveBuffer()
                self.received=0
                self.gain=0
            def put(self,frame):
                self.received+=1
            def start(self):
                pass
            def close(self):
                pass

        def worker(i,process):
            try:
                run_radio(network.clients[i].folder,process,stop,lambda state: None,
                          lambda output: outputs.__setitem__(i,output),lambda: 0.5)
            except Exception as error:
                failures.append(error)

        def drive(predicate,timeout=5):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline and not failures:
                network.now=int(time.time()*1000)
                network.tick()
                if predicate():
                    return True
                time.sleep(0.02)
            return False

        threads=[]
        try:
            with patch('radio_audio.PearAPI',API),patch('radio_audio.PearCapture',Capture),patch('radio_audio.AudioOutput',Output):
                for i,process in [(0,dict(pid=123,create_time=1)),(1,None)]:
                    thread=threading.Thread(target=worker,args=(i,process),daemon=True)
                    threads.append(thread)
                    thread.start()
                self.assertTrue(drive(lambda: network.clients[0].lua.eval('AfterdarkRadioClient.state.ready==true')))
                network.clients[0].lua.execute('AfterdarkRadioClient.send("radio_use",part)')
                network.flush()
                self.assertTrue(drive(lambda: 1 in outputs and outputs[1].received>=2),failures)
                self.assertEqual(len(apis),1)
                self.assertTrue(drive(lambda: 'play' in apis[0].actions),failures)
                self.assertEqual(outputs[1].gain,0.5)
                network.server.lua.globals().part.data.volume=0.4
                self.assertTrue(drive(lambda: 40 in apis[0].volumes),failures)
                self.assertEqual(outputs[1].gain,0.5)
                network.clients[1].lua.execute('AfterdarkRadioClient.send("radio_control",part,"pause")')
                network.flush()
                self.assertTrue(drive(lambda: 'pause' in apis[0].actions),failures)
                self.assertTrue(drive(lambda: outputs[1].gain==0))
                stop.set()
                for thread in threads:
                    thread.join(timeout=4)
        finally:
            stop.set()
            for thread in threads:
                thread.join(timeout=4)
            network.temporary.cleanup()
        self.assertEqual(failures,[])
        self.assertFalse(any(thread.is_alive() for thread in threads))


@unittest.skipUnless(LuaRuntime, 'Optional Lua harness requires lupa')
class RadioNetworkTests(unittest.TestCase):
    car = dict(kind='car', vehicle=7)
    world = dict(kind='world', x=20, y=20, z=0, index=0)

    def setUp(self):
        self.network = Network(radio=True)
        self.addCleanup(self.network.temporary.cleanup)
        self.keys = {i: str(i+1)*32 for i in range(3)}
        self.reports = {i: dict(ready='1') for i in range(3)}
        self.requests = {i: 0 for i in range(3)}
        self.tick()
        self.tick(200)

    def tick(self, milliseconds=0):
        self.network.now += milliseconds
        for i, realm in self.network.clients.items():
            if self.reports[i] is not None:
                write_snapshot(realm.folder / 'Lua/AfterdarkGame.control.txt', dict(
                    serial=1, client=self.keys[i], role='radio', timestamp=self.network.now, **self.reports[i]))
        self.network.tick()

    def command(self, player, command, ref=None, **extra):
        self.requests[player] += 1
        self.network.command(player, command, dict(client=self.keys[player], source=ref or self.car,
                                                  request=self.requests[player], **extra))

    def state(self, player=0):
        return self.network.clients[player].lua.globals().AfterdarkRadioClient.state

    def use(self, player=0, ref=None):
        self.command(player, 'radio_use', ref)
        return self.state(player).room

    def audio(self, player, room, sequence=0):
        self.network.command(player, 'audio', dict(client=self.keys[player], room=room,
                                                  sequence=sequence, payload=pack_batch([b'one', b'two'])))

    def globals(self):
        return self.network.server.lua.globals()

    def test_only_occupants_can_take_over_and_old_owner_audio_is_rejected(self):
        room = self.use()
        self.globals().players[2].vehicle = None
        self.globals().players[2].x = 200
        self.use(2)
        self.assertEqual(self.state().room, room)
        next_room = self.use(1)
        self.assertNotEqual(next_room, room)
        self.network.delivered.clear()
        self.audio(0, room)
        self.assertFalse(any(message[0] == 'server' and message[2] == 'audio' for message in self.network.delivered))
        self.audio(1, next_room)
        self.assertTrue(any(message[0] == 'server' and message[1] == 0 and message[2] == 'audio'
                            for message in self.network.delivered))

    def test_commands_require_current_room_and_are_queued_in_order_until_ack(self):
        room = self.use()
        self.command(1, 'radio_control', room='old_room', action='next')
        self.assertEqual(self.state().command_id, 0)
        self.tick(310)
        self.command(1, 'radio_control', room=room, action='next')
        self.tick(310)
        self.command(1, 'radio_control', room=room, action='previous')
        self.assertEqual(self.state().action, 'next')
        self.assertEqual(self.state().command_id, 1)
        self.reports[0].update(report_room=room, command_ack=1)
        self.tick(1000)
        self.assertEqual(self.state().action, 'previous')
        self.assertEqual(self.state().command_id, 2)

    def test_world_radio_requires_proximity_and_removed_object_ends_session(self):
        self.globals().players[0].vehicle = None
        room = self.use(ref=self.world)
        self.assertTrue(room)
        self.globals().players[1].vehicle = None
        self.globals().players[1].x = 30
        self.use(1, self.world)
        self.assertEqual(self.state().room, room)
        self.globals().objects[1] = None
        self.tick(300)
        self.assertEqual(self.state().room, '')

    def test_power_loss_and_station_switch_clear_ownership(self):
        self.use()
        self.globals().part.data.power = False
        self.tick(300)
        self.assertEqual(self.state().room, '')
        self.globals().part.data.power = True
        self.tick(310)
        self.use()
        self.globals().part.data.channel = 101200
        self.tick(300)
        self.assertEqual(self.state().room, '')

    def test_unready_connector_cannot_take_ownership(self):
        self.reports[0]['ready'] = '0'
        self.tick(1000)
        self.assertEqual(self.use(), '')

    def test_using_own_pear_again_keeps_existing_session(self):
        room=self.use()
        self.tick(310)
        self.assertEqual(self.use(),room)

    def test_duplicate_action_is_not_queued_twice_and_pause_blocks_audio(self):
        room = self.use()
        self.command(1, 'radio_control', room=room, action='pause')
        self.assertTrue(self.state().paused)
        self.network.command(1,'radio_control',dict(client=self.keys[1], source=self.car,
                             request=self.requests[1],room=room,action='pause'))
        self.assertEqual(self.state().command_id,1)
        self.network.delivered.clear()
        self.audio(0,room)
        self.assertFalse(any(message[0]=='server' and message[2]=='audio' for message in self.network.delivered))

    def test_vehicle_and_world_sessions_coexist_and_listener_follows_occupied_car(self):
        room = self.use()
        self.globals().players[1].vehicle=None
        world_room=self.use(1,self.world)
        self.assertNotEqual(room,world_room)
        self.assertEqual(self.state(2).room,room)
        self.assertEqual(self.state(1).room,world_room)

    def test_radio_audio_rejects_replay_and_bounds_a_flood(self):
        room=self.use()
        self.network.delivered.clear()
        self.audio(0,'old_room')
        self.network.command(0,'audio',dict(client=self.keys[0],room=room,sequence=0,payload='invalid'))
        for sequence in range(35):
            self.audio(0,room,sequence)
        self.audio(0,room,0)
        deliveries=[m for m in self.network.delivered if m[0]=='server' and m[2]=='audio']
        self.assertEqual(len(deliveries),60)

    def test_replacing_world_object_at_same_index_does_not_inherit_session(self):
        self.globals().players[0].vehicle=None
        self.use(ref=self.world)
        self.network.server.lua.execute('replacement={}; for k,v in pairs(world) do replacement[k]=v end; objects[1]=replacement')
        self.tick(300)
        self.assertEqual(self.state().room,'')

    def test_listener_gain_fades_after_leaving_car_and_owner_keeps_streaming(self):
        room = self.use()
        self.assertEqual(self.state(1).gain, 1)
        self.globals().players[1].vehicle = None
        self.globals().players[1].x = 30
        self.globals().players[0].vehicle = None
        self.tick(300)
        self.assertGreater(self.state(1).gain, 0)
        self.assertLess(self.state(1).gain, 1)
        self.assertEqual(self.state().room, room)
        self.globals().players[1].x = 100
        self.tick(300)
        self.assertEqual(self.state(1).room, '')

    def test_shared_volume_is_applied_at_source_without_double_attenuation(self):
        self.use()
        self.globals().part.data.volume=0.4
        self.tick(300)
        self.assertEqual(self.state().volume,40)
        self.assertEqual(self.state(1).gain,1)
        self.globals().part.data.volume=0
        self.tick(300)
        self.assertEqual(self.state().volume,0)
        self.assertEqual(self.state(1).room,'')

    def test_connector_timeout_stops_owner_without_selecting_someone_else(self):
        self.use()
        self.reports[0] = None
        self.tick(3100)
        self.assertEqual(self.state(1).room, '')

    def test_noise_requires_fresh_owner_playback_and_audio_at_source(self):
        room = self.use()
        self.tick(1000)
        self.assertEqual(len(self.globals().noise), 0)
        self.reports[0].update(report_room=room, playing='1')
        self.tick(1000)
        self.audio(0, room)
        self.tick(1000)
        self.assertEqual(len(self.globals().noise), 0)
        for sequence in range(1, 31):
            self.audio(0, room, sequence)
            self.tick(40)
        self.assertGreater(len(self.globals().noise), 0)
        self.assertEqual(self.globals().noise[1].x, 20)

    @unittest.skipUnless(importlib.util.find_spec('av'), 'Streaming build requires PyAV')
    def test_real_radio_audio_crosses_lua_authority_and_listener_files(self):
        source = GameBridge(self.network.clients[0].folder, 'radio', clock=lambda: self.network.now/1000)
        listener = GameBridge(self.network.clients[1].folder, 'radio', clock=lambda: self.network.now/1000)
        self.addCleanup(source.close)
        self.addCleanup(listener.close)
        self.keys[0], self.keys[1] = source.client, listener.client
        self.tick(1000)
        room = self.use()
        self.tick(210)
        source.publish(bytes(PCM_BYTES))
        source.publish(bytes(PCM_BYTES))
        self.tick(40)
        self.assertEqual(len(listener.receive()), 2)
        self.assertEqual(source.sent, 1)
        self.assertEqual(listener.received, 1)
        self.assertEqual(listener.heartbeat()['room'], room)


@unittest.skipUnless(LuaRuntime, 'Optional Lua harness requires lupa')
class RadioUITests(unittest.TestCase):
    def test_radio_module_is_added_and_buttons_target_the_open_device(self):
        from test_lua import HARNESS
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(HARNESS)
        lua.execute('''
            client=true
            Events.OnTick.Add=function(fn) table.insert(Events.OnTick.handlers,fn) end
            Events.OnTick.emit=function() for _,fn in ipairs(Events.OnTick.handlers) do fn() end end
        ''')
        lua.execute((LUA / 'shared/AfterdarkGameProtocol.lua').read_text())
        lua.execute((LUA / 'shared/AfterdarkRadioDevices.lua').read_text())
        lua.execute((LUA / 'client/AfterdarkRadioClient.lua').read_text())
        lua.execute((LUA / 'client/AfterdarkRadioUI.lua').read_text())
        lua.execute('''
            sent={}
            function sendClientCommand(module,command,args) table.insert(sent,{command=command,args=args}) end
            AfterdarkRadioDevices.station(94600)
            AfterdarkRadioClient.control={client=string.rep('a',32),role='radio',timestamp=tostring(now),ready='1'}
            AfterdarkRadioClient.state={room='radio_one',key='car_12',owner='Owner',paused=false}
            window=setmetatable({width=330},{__index=ISRadioWindow})
            window:createChildren()
            panel=window.pearModule
            panel:createChildren()
            device.getIsTelevision=function() return false end
            panel:readFromObject(player,part,device,'VehiclePart')
            queued={}
            ISTimedActionQueue={add=function(action) table.insert(queued,action) end}
            ISRadioAction={new=function(self,mode,p,d,frequency) return {mode=mode,frequency=frequency} end}
            channel=101200
            window.device=part; window.player=player; window.deviceData=device
            ISRadioWindow.instancesIso={[0]=window}
            panel:onTune()
            panel:onUse(); panel:onNext(); panel:onPause(); panel:onRelease()
        ''')
        self.assertTrue(lua.eval('window.vanillaCreated'))
        self.assertEqual(lua.eval('sent[1].command'),'radio_use')
        self.assertEqual(lua.eval('sent[1].args.source.vehicle'),12)
        self.assertEqual(lua.eval('sent[2].args.action'),'next')
        self.assertEqual(lua.eval('sent[3].args.action'),'pause')
        self.assertEqual(lua.eval('sent[4].args.action'),'release')
        self.assertEqual(lua.eval('queued[1].mode'),'SetChannel')
        self.assertEqual(lua.eval('queued[1].frequency'),94600)
        lua.execute('channel=94600; Events.OnTick.emit()')
        self.assertEqual(lua.eval('window.afterdarkChannel'),94600)
        self.assertEqual(lua.eval('window.readPresetCount'),2)

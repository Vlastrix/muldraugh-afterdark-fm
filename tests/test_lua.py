"""Execute the Lua against a small game API harness, without starting Zomboid.

Optional developer dependency: pip install --target .tools lupa
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".tools"))
try:
    # Match the game's Lua 5.1 syntax rather than testing only a newer runtime.
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None

SOURCE = Path(__file__).resolve().parents[1] / "mod" / "PearCarRadio" / "common" / "media" / "lua" / "client" / "PearCarRadio.lua"

HARNESS = r'''
now = 1700000000000
client = false
server = false
seated = true
dead = false
powered = true
battery = true
loaded = true
radioInstalled = true
playerX = 10
playerY = 20
playerZ = 0
speed = 1
volume = 0.4
noiseCount = 0
noiseRadius = 0
emitterVolume = 1
emitterResets = 0
channel = 101200
signalRefreshes = 0
presetsSent = 0
stationNames = {}
local function list(items)
    return {
        items=items,
        size=function(self) return #self.items end,
        get=function(self, i) return self.items[i+1] end,
    }
end
function preset(name, freq)
    return {name=name, frequency=freq,
        getName=function(self) return self.name end,
        setName=function(self, name) self.name=name end,
        getFrequency=function(self) return self.frequency end,
        setFrequency=function(self, f) self.frequency=f end}
end
presets = {
    entries=list({preset("KnoxTalk Radio",101200)}), max=10,
    getPresets=function(self) return self.entries end,
    getMaxPresets=function(self) return self.max end,
    addPreset=function(self, name, freq) table.insert(self.entries.items,preset(name,freq)) end,
}
function getZomboidRadio()
    return {
        getChannelName=function(self, f) return stationNames[f] end,
        addChannelName=function(self, name, f, category, overwrite)
            if overwrite or not stationNames[f] then stationNames[f]=name end
        end,
    }
end
function instanceof(object, name) return object == part and name == "VehiclePart" end
files = {}
denyWrites = false
UIFont = {Small = 1}
function require(name) end
function getTimestampMs() return now end
function isClient() return client end
function isServer() return server end
function getGameSpeed() return speed end
function getCell()
    return {getVehicles=function() return {contains=function(self, v) return loaded and v == vehicle end} end}
end
function addSound(player, x, y, z, radius, strength)
    noiseCount = noiseCount + 1
    noiseRadius = radius
end
function getFileWriter(name, create, append)
    local extension = name:match("%.([^%.]+)$")
    local allowed = {ini=true, cfg=true, txt=true, log=true, json=true}
    if denyWrites or not allowed[extension] then return nil end
    local content = ""
    return {
        write = function(self, value) content = content .. value end,
        close = function(self) files[name] = content end,
    }
end
function getFileReader(name, create)
    local content = files[name]
    if not content then return nil end
    local lines = {}
    for line in content:gmatch("([^\n]+)") do table.insert(lines, line) end
    local i = 0
    return {readLine = function(self) i = i + 1; return lines[i] end, close = function(self) end}
end
device = {
    doReceiveSignal = function(self, distance) signalRefreshes=signalRefreshes+1 end,
    getChannel = function() return channel end,
    setChannel = function(self, f) channel=f end,
    getMinChannelRange = function() return 88000 end,
    getMaxChannelRange = function() return 108000 end,
    getDevicePresets = function() return presets end,
    transmitPresets = function() presetsSent=presetsSent+1 end,
    getIsTurnedOn = function() return powered end,
    canBePoweredHere = function() return battery end,
    getDeviceVolume = function() return volume end,
    getEmitter = function() return {setVolumeAll=function(self, v) emitterVolume=v end} end,
    cleanSoundsAndEmitter = function() emitterResets=emitterResets+1; emitterVolume=1 end,
}
vehicle = {
    getId = function() return 12 end,
    getX = function() return 10 end,
    getY = function() return 20 end,
    getZ = function() return 0 end,
    getPartById = function(self, id) return part end,
}
part = {
    getInventoryItem = function() if radioInstalled then return {} end end,
    getDeviceData = function() return device end,
    getVehicle = function() return vehicle end,
    -- Match the real engine: this Java object's members are not exposed to Lua.
    getChatElement = function()
        return setmetatable({}, {__index=function() error("ChatElement not exposed") end})
    end,
}
player = {
    getX = function() return playerX end,
    getY = function() return playerY end,
    getZ = function() return playerZ end,
    isDead = function() return dead end,
    getPlayerNum = function() return 0 end,
    getVehicle = function() if seated then return vehicle end end,
}
function getSpecificPlayer(n) return player end
local Option = {getValue = function(self) return self.value end}
PZAPI = {ModOptions = {create = function()
    return {
        addDescription = function() end,
        addTickBox = function(self, id, label, value)
            return setmetatable({value=value}, {__index=Option})
        end,
    }
end}}
local function event()
    return {handlers={}, Add=function(fn) end}
end
Events = {OnTick=event(), OnGameStart=event(), OnMainMenuEnter=event()}
function getTextManager()
    return {getFontHeight=function() return 14 end}
end
local Base = {}
Base.__index = Base
function Base:derive(name)
    local class = {}
    class.__index = class
    return setmetatable(class, {__index=self})
end
function Base:new(x, y, width, height)
    return setmetatable({x=x,y=y,width=width,height=height,children={}}, self)
end
function Base:setHeight(height) self.height=height end
function Base:addChild(child) table.insert(self.children, child) end
function Base:initialise() end
function Base:setTitle(title) self.title=title end
function Base:setEnable(value) self.enable=value end
function Base:prerender() end
function Base:setStencilRect() end
function Base:clearStencilRect() end
function Base:drawText() end
function Base:doWalkTo() return true end
function Base:readFromObject(p, object, data, kind)
    self.player=p; self.device=object; self.deviceData=data; self.deviceType=kind
end
RWMPanel = Base
ISButton = Base:derive("ISButton")
RWMChannel = {
    addComboOption=function(self, f, name) self.comboBox:addOption("vanilla:" .. name) end,
}
ISRadioWindow = {
    createChildren=function(self) self.vanillaCreated=true end,
    addModule=function(self, module, title, enabled) self.pearModule=module end,
    readFromObject=function(self, p, d) self.readPresetCount=presets.entries:size() end,
}
'''


@unittest.skipIf(LuaRuntime is None, "Optional Lua 5.1 harness requires lupa in .tools")
class LuaTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(HARNESS)
        self.lua.execute(SOURCE.read_text(encoding="utf-8"))

    def evaluate(self, expression):
        return self.lua.eval(expression)

    def execute(self, text):
        self.lua.execute(text)

    def control(self):
        content = self.evaluate('files["PearCarRadio.control.txt"]')
        return dict(line.split("=", 1) for line in content.splitlines())

    def test_opt_in_power_volume_and_music_continues_outside(self):
        self.execute("PearCarRadio.tick()")
        self.assertEqual(self.control()["active"], "0")
        self.execute('PearCarRadio.registerStation(); channel=PearCarRadio.frequency; now=now+500; PearCarRadio.tick()')
        self.assertEqual(self.control()["playing"], "1")
        self.assertEqual(self.control()["volume"], "40")
        self.execute("powered=false; now=now+500; PearCarRadio.tick()")
        self.assertEqual(self.control()["playing"], "0")
        self.execute("powered=true; seated=false; now=now+500; PearCarRadio.tick()")
        self.assertEqual(self.control()["active"], "1")
        self.assertEqual(self.control()["playing"], "1")
        self.assertEqual(self.control()["volume"], "40")

    def test_outside_volume_fades_with_distance_without_pausing_song(self):
        self.execute('PearCarRadio.tuneStation(device,"12"); PearCarRadio.tick(); seated=false')
        volumes = []
        for distance in (0, 3, 7, 10, 14, 25):
            self.execute('playerX=10+{}; now=now+500; PearCarRadio.tick()'.format(distance))
            volumes.append(int(self.control()["volume"]))
            self.assertEqual(self.control()["playing"], "1")
            self.assertEqual(self.control()["vehicle"], "12")
        self.assertEqual(volumes, sorted(volumes, reverse=True))
        self.assertEqual(volumes[0], 40)
        self.assertEqual(volumes[2], 20)
        self.assertEqual(volumes[-1], 0)
        self.execute('seated=true; now=now+500; PearCarRadio.tick()')
        self.assertEqual(self.control()["volume"], "40")

    def test_unloaded_car_releases_reference_and_stops_pear(self):
        self.execute('PearCarRadio.tuneStation(device,"12"); PearCarRadio.tick()')
        self.execute('seated=false; loaded=false; now=now+500; PearCarRadio.tick()')
        self.assertEqual(self.control()["active"], "0")
        self.assertIsNone(self.evaluate("PearCarRadio.sourceVehicle"))
        self.assertIsNone(self.evaluate("PearCarRadio.mutedDevice"))
        # The emitter may have been recycled; do not clean it after unload.
        self.assertEqual(self.evaluate("emitterResets"), 0)

    def test_outside_power_battery_and_radio_removal_stop_music(self):
        for change in ('powered=false', 'battery=false', 'radioInstalled=false'):
            with self.subTest(change=change):
                self.setUp()
                self.execute('PearCarRadio.tuneStation(device,"12"); PearCarRadio.tick(); seated=false')
                self.execute(change + '; now=now+500; PearCarRadio.tick()')
                self.assertEqual(self.control()["playing"], "0")

    def test_death_and_stop_forget_parked_vehicle(self):
        for change in ('dead=true; now=now+500; PearCarRadio.tick()', 'PearCarRadio.stop()'):
            with self.subTest(change=change):
                self.setUp()
                self.execute('PearCarRadio.tuneStation(device,"12"); PearCarRadio.tick(); seated=false')
                self.execute(change)
                self.assertEqual(self.control()["playing"], "0")
                self.assertIsNone(self.evaluate("PearCarRadio.sourceVehicle"))

    def test_outside_zombie_noise_uses_car_volume_not_listener_distance(self):
        self.execute(r'''
            PearCarRadio.tuneStation(device,"12")
            PearCarRadio.tick()
            seated=false; playerX=100; now=now+1000
            files["PearCarRadio.status.txt"]="timestamp=" .. tostring(now/1000)
                .. "\nsession=" .. PearCarRadio.session .. "\nplaying=1\n"
            PearCarRadio.tick()
        ''')
        self.assertEqual(self.control()["volume"], "0")
        self.assertEqual(self.control()["playing"], "1")
        self.assertEqual(self.evaluate("noiseCount"), 1)
        self.assertEqual(self.evaluate("noiseRadius"), 14)

    def test_entering_other_car_does_not_keep_parked_car_as_source(self):
        self.execute('''
            PearCarRadio.tuneStation(device,"12")
            PearCarRadio.tick()
            otherDevice=setmetatable({getChannel=function() return 101200 end}, {__index=device})
            otherPart={getInventoryItem=function() return {} end, getDeviceData=function() return otherDevice end}
            otherVehicle={getId=function() return 99 end, getPartById=function() return otherPart end}
            player.getVehicle=function() return otherVehicle end
            now=now+500
            PearCarRadio.tick()
        ''')
        self.assertEqual(self.control()["active"], "0")
        self.assertIsNone(self.evaluate("PearCarRadio.sourceVehicle"))

    def test_no_bridge_writes_in_multiplayer(self):
        self.execute('client=true; PearCarRadio.tick()')
        self.assertIsNone(self.evaluate('files["PearCarRadio.control.txt"]'))

    def test_game_writer_rejects_old_extension_but_mod_uses_txt(self):
        self.assertIsNone(self.evaluate('getFileWriter("PearCarRadio.control", true, false)'))
        self.execute('PearCarRadio.tick()')
        self.assertEqual(self.control()["protocol"], "1")
        self.assertIsNone(self.evaluate("PearCarRadio.fileError"))

    def test_failed_writer_reports_error(self):
        self.execute('denyWrites=true; PearCarRadio.tick()')
        self.assertIsNotNone(self.evaluate("PearCarRadio.fileError"))

    def test_vanilla_radio_stays_muted_outside_and_restored_on_channel_change(self):
        self.execute('PearCarRadio.tick()')
        self.assertEqual(self.evaluate("emitterVolume"), 1)
        self.execute('PearCarRadio.registerStation(); channel=PearCarRadio.frequency; now=now+500; PearCarRadio.tick()')
        self.assertEqual(self.evaluate("emitterVolume"), 0)
        self.assertEqual(self.evaluate("volume"), 0.4)
        self.execute('seated=false; now=now+500; PearCarRadio.tick()')
        self.assertEqual(self.evaluate("emitterVolume"), 0)
        self.execute('channel=101200; now=now+500; PearCarRadio.tick()')
        self.assertEqual(self.evaluate("emitterVolume"), 1)
        self.assertEqual(self.evaluate("emitterResets"), 1)

    def test_station_added_before_channel_dropdown_is_built(self):
        self.execute('''
            window=setmetatable({}, {__index=ISRadioWindow})
            window:readFromObject(player,part)
            window:readFromObject(player,part)
        ''')
        self.assertEqual(self.evaluate("window.readPresetCount"), 2)
        self.assertEqual(self.evaluate("presetsSent"), 1)
        self.assertEqual(self.evaluate('stationNames[94460]'), "Muldraugh Afterdark FM")
        self.assertEqual(self.evaluate('presets.entries:get(1):getFrequency()'), 94460)

    def test_legacy_preset_migrates_in_place_and_retunes_saved_radio(self):
        self.execute('''
            table.insert(presets.entries.items, preset("Pear FM", 94000))
            presets.max=2
            channel=94000
            PearCarRadio.ensurePreset(device)
            PearCarRadio.ensurePreset(device)
        ''')
        self.assertEqual(self.evaluate('presets.entries:size()'), 2)
        self.assertEqual(self.evaluate('presets.entries:get(0):getName()'), "KnoxTalk Radio")
        self.assertEqual(self.evaluate('presets.entries:get(1):getName()'), "Muldraugh Afterdark FM")
        self.assertEqual(self.evaluate('channel'), 94460)
        self.assertEqual(self.evaluate('presetsSent'), 1)

    def test_dropdown_keeps_46_decimals_without_changing_other_stations(self):
        self.execute('''
            PearCarRadio.registerStation()
            labels={}
            local panel=setmetatable({comboBox={addOption=function(self, text)
                table.insert(labels,text)
            end}}, {__index=RWMChannel})
            panel:addComboOption(94460,PearCarRadio.stationName)
            panel:addComboOption(101200,"KnoxTalk Radio")
        ''')
        self.assertEqual(self.evaluate('labels[1]'), "94.46 MHz Afterdark FM")
        self.assertEqual(self.evaluate('labels[2]'), "vanilla:KnoxTalk Radio")

    def test_all_fallback_frequencies_keep_46_and_stay_within_fm_band(self):
        self.execute('''
            for i=1,20 do
                PearCarRadio.frequency=nil
                assert(PearCarRadio.registerStation())
                local f=PearCarRadio.frequency
                assert(f>=88000 and f<=108000 and f%1000==460)
                stationNames[f]="Occupied " .. tostring(i)
            end
            PearCarRadio.frequency=nil
            exhausted=not PearCarRadio.registerStation()
        ''')
        self.assertTrue(self.evaluate('exhausted'))

    def test_frequency_collision_preserves_other_station(self):
        self.execute('stationNames[94460]="Another mod FM"; PearCarRadio.ensurePreset(device)')
        self.assertEqual(self.evaluate("PearCarRadio.frequency"), 95460)
        self.assertEqual(self.evaluate("stationNames[94460]"), "Another mod FM")

    def test_full_presets_are_preserved_and_button_can_still_tune(self):
        self.execute('presets.max=1; PearCarRadio.tuneStation(device,"12")')
        self.assertEqual(self.evaluate("presets.entries:size()"), 1)
        self.assertEqual(self.evaluate("channel"), 94460)
        self.execute('PearCarRadio.leaveStation(device,"12")')
        self.assertEqual(self.evaluate("channel"), 101200)

    def test_native_channel_tuning_controls_pear_without_opt_in_button(self):
        self.execute('PearCarRadio.registerStation(); channel=PearCarRadio.frequency; PearCarRadio.tick()')
        self.assertEqual(self.control()["playing"], "1")
        self.execute('channel=101200; now=now+500; PearCarRadio.tick()')
        self.assertEqual(self.control()["active"], "0")
        self.assertEqual(self.evaluate("emitterVolume"), 1)

    def test_station_receives_signal_without_accessing_unexposed_chat(self):
        self.execute('PearCarRadio.tick()')
        self.assertEqual(self.evaluate("signalRefreshes"), 0)
        self.execute('PearCarRadio.registerStation(); channel=PearCarRadio.frequency; speed=0; PearCarRadio.tick()')
        self.assertEqual(self.evaluate("signalRefreshes"), 1)
        # Audio is muted every frame, not just each file heartbeat.
        self.execute('PearCarRadio.tick()')
        self.assertEqual(self.evaluate("signalRefreshes"), 2)
        self.execute('channel=101200; PearCarRadio.tick()')
        self.assertEqual(self.evaluate("signalRefreshes"), 2)

    def test_optional_signal_failure_does_not_block_ui_or_heartbeat_or_repeat(self):
        self.execute('''
            failures=0
            device.doReceiveSignal=function() failures=failures+1; error("not exposed") end
            PearCarRadio.tuneStation(device,"12")
            PearCarRadio.tick()
            panel=RWMPearCarRadio:new(0,0,300,0)
            panel:createChildren()
            panel:readFromObject(player,part,device,"VehiclePart")
            now=now+500
            panel:prerender()
        ''')
        self.assertEqual(self.control()["playing"], "1")
        self.assertEqual(self.evaluate("failures"), 1)
        self.assertEqual(self.evaluate("panel.useButton.title"), "Return to previous station")
        self.assertTrue(self.evaluate("panel.pauseButton.enable"))

    def test_signal_not_generated_for_radio_without_power(self):
        self.execute('PearCarRadio.tuneStation(device,"12"); powered=false; PearCarRadio.tick()')
        self.assertEqual(self.evaluate("signalRefreshes"), 0)
        self.execute('powered=true; battery=false; now=now+500; PearCarRadio.tick()')
        self.assertEqual(self.evaluate("signalRefreshes"), 0)

    def test_return_to_previous_station_from_shortcut(self):
        self.execute('''
            PearCarRadio.tuneStation(device,"12")
            PearCarRadio.tick()
            PearCarRadio.leaveStation(device,"12")
            now=now+500
            PearCarRadio.tick()
        ''')
        self.assertEqual(self.evaluate("channel"), 101200)
        self.assertEqual(self.control()["active"], "0")

    def test_activation_sends_state_immediately_while_paused(self):
        self.execute('''
            speed=0
            panel=RWMPearCarRadio:new(0,0,300,0)
            panel:createChildren()
            panel:readFromObject(player,part,device,"VehiclePart")
            panel:onUse()
        ''')
        self.assertEqual(self.control()["active"], "1")
        self.assertEqual(self.control()["playing"], "0")
        self.execute('speed=1; now=now+500; panel:prerender()')
        self.assertEqual(self.control()["playing"], "1")

    def test_noise_requires_fresh_confirmed_song(self):
        self.execute('PearCarRadio.registerStation(); channel=PearCarRadio.frequency; PearCarRadio.tick()')
        self.assertEqual(self.evaluate("noiseCount"), 0)
        self.execute(r'''
            now=now+1000
            files["PearCarRadio.status.txt"]="timestamp=" .. tostring(now/1000)
                .. "\nsession=" .. PearCarRadio.session .. "\nplaying=1\n"
            PearCarRadio.tick()
        ''')
        self.assertEqual(self.evaluate("noiseCount"), 1)
        self.assertEqual(self.evaluate("noiseRadius"), 14)
        self.execute("now=now+6000; PearCarRadio.tick()")
        self.assertEqual(self.evaluate("noiseCount"), 1)

    def test_old_session_cannot_generate_noise(self):
        self.execute(r'''
            PearCarRadio.registerStation(); channel=PearCarRadio.frequency
            files["PearCarRadio.status.txt"]="timestamp=" .. tostring(now/1000)
                .. "\nsession=old\nplaying=1\n"
            PearCarRadio.tick()
        ''')
        self.assertEqual(self.evaluate("noiseCount"), 0)

    def test_panel_is_added_to_vanilla_window_and_operates(self):
        self.execute('''
            window=setmetatable({}, {__index=ISRadioWindow})
            window:createChildren()
            panel=RWMPearCarRadio:new(0,0,300,0)
            panel:createChildren()
            visible=panel:readFromObject(player,part,device,"VehiclePart")
            panel:onUse()
            panel:onNext()
            panel:prerender()
        ''')
        self.assertTrue(self.evaluate("window.vanillaCreated"))
        self.assertTrue(self.evaluate("window.pearModule ~= nil"))
        self.assertTrue(self.evaluate("visible"))
        self.assertEqual(self.evaluate("PearCarRadio.selectedVehicle"), "12")
        self.assertEqual(self.evaluate("PearCarRadio.action"), "next")
        self.execute("panel:onPause(); PearCarRadio.tick()")
        self.assertEqual(self.control()["playing"], "0")
        self.execute("panel:onUse()")
        self.assertIsNone(self.evaluate("PearCarRadio.selectedVehicle"))

    def test_status_decodes_percent_and_unicode(self):
        self.execute(r'''
            files["PearCarRadio.status.txt"]="timestamp=" .. tostring(now/1000)
                .. "\ntitle=Music%20%E2%99%AB%20%26%20pop\n"
            PearCarRadio.readStatus()
        ''')
        self.assertEqual(self.evaluate("PearCarRadio.status.title"), "Music ♫ & pop")


if __name__ == "__main__":
    unittest.main()

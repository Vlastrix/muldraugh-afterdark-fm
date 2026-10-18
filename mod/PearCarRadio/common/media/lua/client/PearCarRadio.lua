require "RadioCom/ISRadioWindow"
require "RadioCom/RadioWindowModules/RWMPanel"
require "ISUI/ISButton"
require "PZAPI/ModOptions"

-- Local files are under Zomboid/Lua. No network calls run on the game thread.
PearCarRadio = PearCarRadio or {}
local Radio = PearCarRadio
Radio.status = {}
Radio.selectedVehicle = nil
Radio.paused = false
Radio.frame = 0
Radio.actionId = 0
Radio.action = "none"
Radio.lastTick = 0
Radio.lastNoise = 0
Radio.session = tostring(getTimestampMs())
Radio.stationName = "Pear FM"
Radio.frequency = nil
Radio.previousChannels = {}
Radio.sourceVehicle = nil

local options = PZAPI.ModOptions:create("PearCarRadio", "Pear Car Radio")
options:addDescription("Abre una cancion o playlist en Pear y ejecuta el puente local. Solo singleplayer.")
local noiseOption = options:addTickBox("zombieNoise", "La musica atrae zombis", true,
    "Agrega ruido en el coche mientras Pear confirma reproduccion. El volumen de la radio controla el alcance.")
local muteOption = options:addTickBox("muteVanilla", "Silenciar audio de la radio original al usar Pear", true,
    "Silencia voces y estatica de esta radio. Conserva el volumen, los canales y los demas sonidos del coche.")

local function encode(value)
    return (tostring(value or ""):gsub("[^%w%-%._~]", function(char)
        return string.format("%%%02X", string.byte(char))
    end))
end

local function decode(value)
    return (value:gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end))
end

function Radio.registerStation()
    if isClient() or isServer() then return false end
    local radio = getZomboidRadio()
    if not radio then return false end
    if Radio.frequency and radio:getChannelName(Radio.frequency) == Radio.stationName then return true end
    -- Stay in the normal FM band without replacing a vanilla/other mod station.
    for offset = 0, 100 do
        local frequency = 88000 + ((30 + offset) % 101) * 200
        local name = radio:getChannelName(frequency)
        if not name or name == Radio.stationName then
            Radio.frequency = frequency
            radio:addChannelName(Radio.stationName, frequency, "Radio", false)
            return true
        end
    end
    Radio.frequency = nil
    return false
end

function Radio.isTuned(device)
    return device ~= nil and Radio.frequency ~= nil and device:getChannel() == Radio.frequency
end

function Radio.ensurePreset(device)
    if not Radio.registerStation() then return false end
    if Radio.frequency < device:getMinChannelRange() or Radio.frequency > device:getMaxChannelRange() then return false end
    local presets = device:getDevicePresets()
    if not presets then return false end
    local entries = presets:getPresets()
    for i = 0, entries:size() - 1 do
        local entry = entries:get(i)
        if entry:getFrequency() == Radio.frequency then return true end
        if entry:getName() == Radio.stationName then
            entry:setFrequency(Radio.frequency)
            device:transmitPresets()
            return true
        end
    end
    -- Do not remove an existing preset when a radio has all its slots filled.
    if entries:size() >= presets:getMaxPresets() then return false end
    presets:addPreset(Radio.stationName, Radio.frequency)
    device:transmitPresets()
    return true
end

function Radio.tuneStation(device, vehicleId)
    Radio.ensurePreset(device)
    if not Radio.frequency then return end
    if not Radio.isTuned(device) then Radio.previousChannels[vehicleId] = device:getChannel() end
    device:setChannel(Radio.frequency)
    Radio.paused = false
    Radio.lastTick = 0
end

function Radio.leaveStation(device, vehicleId)
    local previous = Radio.previousChannels[vehicleId]
    if not previous or previous == Radio.frequency then
        local presets = device:getDevicePresets()
        local entries = presets and presets:getPresets()
        if entries then
            for i = 0, entries:size() - 1 do
                if entries:get(i):getFrequency() ~= Radio.frequency then
                    previous = entries:get(i):getFrequency()
                    break
                end
            end
        end
    end
    if not previous or previous == Radio.frequency then
        previous = device:getMinChannelRange()
        if previous == Radio.frequency then previous = device:getMaxChannelRange() end
    end
    device:setChannel(previous)
    Radio.lastTick = 0
end

function Radio.readStatus()
    local file = getFileReader("PearCarRadio.status.txt", false)
    if not file then Radio.status = {}; return end
    local status = {}
    local line = file:readLine()
    local count = 0
    while line and count < 24 do
        local key, value = line:match("^([%w_]+)=(.*)$")
        if key then status[key] = decode(value) end
        count = count + 1
        line = file:readLine()
    end
    file:close()
    local timestamp = tonumber(status.timestamp or "0") or 0
    if math.abs(getTimestampMs() / 1000 - timestamp) > 5 then
        Radio.status = {}
    else
        Radio.status = status
    end
end

function Radio.getVehicleRadio()
    if isClient() or isServer() then return nil end
    local player = getSpecificPlayer(0)
    if not player or player:isDead() then Radio.sourceVehicle = nil; return nil end
    local vehicle = player:getVehicle()
    if not vehicle then
        vehicle = Radio.sourceVehicle
        local cell = getCell()
        if vehicle and (not cell or not cell:getVehicles():contains(vehicle)) then
            -- Never retain/access an unloaded vehicle or its recycled emitter.
            Radio.sourceVehicle = nil
            Radio.mutedDevice = nil
            return nil
        end
    end
    if not vehicle then return nil end
    local part = vehicle:getPartById("Radio")
    if not part or not part:getInventoryItem() or not part:getDeviceData() then
        Radio.sourceVehicle = nil
        return nil
    end
    return player, vehicle, part, part:getDeviceData()
end

function Radio.listenerVolume(player, vehicle, volume)
    if volume <= 0 then return 0 end
    if player:getVehicle() == vehicle then return volume end
    local dx = player:getX() - vehicle:getX()
    local dy = player:getY() - vehicle:getY()
    local dz = (player:getZ() - vehicle:getZ()) * 3
    local distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    local radius = math.max(1, 35 * volume / 100)
    local t = math.min(1, distance / radius)
    local gain = 1 - t * t * (3 - 2 * t)
    return math.floor(volume * gain + 0.5)
end

function Radio.sendAction(action)
    Radio.actionId = Radio.actionId + 1
    Radio.action = action
    Radio.lastTick = 0
end

function Radio.writeState(active, playing, volume, vehicleId)
    Radio.frame = Radio.frame + 1
    -- B42.21 allows writes only to ini/cfg/txt/log/json extensions.
    local file = getFileWriter("PearCarRadio.control.txt", true, false)
    if not file then
        if not Radio.fileError then print("[PearCarRadio] No se pudo escribir PearCarRadio.control.txt") end
        Radio.fileError = "No se puede escribir la senal del mod. Revisa console.txt."
        return
    end
    Radio.fileError = nil
    local values = {
        {"protocol", "1"}, {"session", Radio.session}, {"frame", Radio.frame},
        {"active", active and "1" or "0"}, {"playing", playing and "1" or "0"},
        {"volume", volume}, {"vehicle", vehicleId or ""},
        {"action_id", Radio.actionId}, {"action", Radio.action},
        {"commit", Radio.frame},
    }
    for _, entry in ipairs(values) do file:write(entry[1] .. "=" .. encode(entry[2]) .. "\n") end
    file:close()
end

function Radio.updateVanillaMute(device)
    local target = muteOption:getValue() and device or nil
    if Radio.mutedDevice and Radio.mutedDevice ~= target then
        -- Discard the muted radio emitter; vanilla recreates it at normal gain.
        Radio.mutedDevice:cleanSoundsAndEmitter()
        Radio.mutedDevice = nil
    end
    if target then
        Radio.mutedDevice = target
        local emitter = target:getEmitter()
        if emitter then emitter:setVolumeAll(0) end
    end
end

function Radio.refreshStationSignal(device)
    if Radio.signalUnsupported or not device:getIsTurnedOn() or not device:canBePoweredHere() then return end
    -- ChatElement is NOT exposed to Kahlua in B42.21, even though VehiclePart
    -- returns it. Give this virtual station a radio signal instead: vanilla's
    -- static-text generator skips devices that are receiving a signal.
    -- Keep this optional feature isolated from the playback heartbeat and UI.
    local ok = pcall(function() device:doReceiveSignal(0) end)
    if not ok then
        Radio.signalUnsupported = true
        print("[PearCarRadio] Senal local no disponible; Pear sigue funcionando sin ocultar estatica.")
    end
end

function Radio.tick()
    if isClient() or isServer() then return end
    local player, vehicle, part, device = Radio.getVehicleRadio()
    local vehicleId = vehicle and tostring(vehicle:getId()) or ""
    if device and not Radio.frequency then Radio.registerStation() end
    local active = Radio.isTuned(device)
    Radio.sourceVehicle = active and vehicle or nil
    if active and Radio.selectedVehicle ~= vehicleId then Radio.paused = false end
    Radio.selectedVehicle = active and vehicleId or nil
    if device and not active then Radio.previousChannels[vehicleId] = device:getChannel() end
    if active then Radio.refreshStationSignal(device) end
    -- Apply each frame: vanilla may start fresh static/talk events between heartbeats.
    Radio.updateVanillaMute(active and device or nil)
    local now = getTimestampMs()
    if now - Radio.lastTick < 500 then return end
    Radio.lastTick = now
    Radio.readStatus()
    local powered = active and device:getIsTurnedOn() and device:canBePoweredHere()
    local playing = powered and not Radio.paused and getGameSpeed() > 0
    local volume = device and math.floor(device:getDeviceVolume() * 100 + 0.5) or 0
    local listenerVolume = active and Radio.listenerVolume(player, vehicle, volume) or 0
    -- At distance zero gain we keep advancing Pear silently, like a real radio.
    Radio.writeState(active, playing, listenerVolume, vehicleId)

    -- Human audio is external; zombie hearing is simulated at the car separately.
    if playing and volume > 0 and noiseOption:getValue()
        and Radio.status.session == Radio.session and Radio.status.playing == "1"
        and now - Radio.lastNoise >= 1000 then
        Radio.lastNoise = now
        local radius = math.max(1, math.floor(35 * volume / 100))
        addSound(player, math.floor(vehicle:getX()), math.floor(vehicle:getY()),
            math.floor(vehicle:getZ()), radius, radius)
    end
end

function Radio.stop()
    Radio.updateVanillaMute(nil)
    Radio.selectedVehicle = nil
    Radio.sourceVehicle = nil
    Radio.paused = false
    Radio.writeState(false, false, 0, "")
end

RWMPearCarRadio = RWMPanel:derive("RWMPearCarRadio")

function RWMPearCarRadio:createChildren()
    self.lineHeight = getTextManager():getFontHeight(UIFont.Small) + 4
    local height = self.lineHeight + 8
    self:setHeight(height * 2 + self.lineHeight * 4 + 26)
    self.useButton = ISButton:new(10, 8, self.width - 20, height,
        "Usar Pear en este coche", self, RWMPearCarRadio.onUse)
    self.useButton:initialise()
    self:addChild(self.useButton)
    local width = (self.width - 28) / 3
    self.previousButton = ISButton:new(10, height + 14, width, height,
        "Anterior", self, RWMPearCarRadio.onPrevious)
    self.pauseButton = ISButton:new(14 + width, height + 14, width, height,
        "Pausa", self, RWMPearCarRadio.onPause)
    self.nextButton = ISButton:new(18 + width * 2, height + 14, width, height,
        "Siguiente", self, RWMPearCarRadio.onNext)
    for _, button in ipairs({self.previousButton, self.pauseButton, self.nextButton}) do
        button:initialise()
        self:addChild(button)
    end
    self.textY = height * 2 + 22
end

function RWMPearCarRadio:readFromObject(player, device, data, deviceType)
    RWMPanel.readFromObject(self, player, device, data, deviceType)
    return not isClient() and not isServer() and deviceType == "VehiclePart"
        and player:getPlayerNum() == 0 and player:getVehicle() == device:getVehicle()
end

function RWMPearCarRadio:isSelected()
    return Radio.isTuned(self.deviceData)
end

function RWMPearCarRadio:onUse()
    if not self:doWalkTo() then return end
    local vehicleId = tostring(self.device:getVehicle():getId())
    if self:isSelected() then
        Radio.leaveStation(self.deviceData, vehicleId)
    else
        Radio.tuneStation(self.deviceData, vehicleId)
    end
    Radio.lastTick = 0
    Radio.tick()
    local windows = ISRadioWindow.instancesIso
    local window = windows and windows[self.player:getPlayerNum()]
    if window and window.device == self.device then
        -- Refresh the stock dropdown as well when using the shortcut button.
        window:readFromObject(self.player, self.device)
    end
end

function RWMPearCarRadio:onPause()
    if not self:isSelected() then return end
    Radio.paused = not Radio.paused
    Radio.lastTick = 0
    Radio.tick()
end

function RWMPearCarRadio:onPrevious() Radio.sendAction("previous") end
function RWMPearCarRadio:onNext() Radio.sendAction("next") end

function RWMPearCarRadio:prerender()
    RWMPanel.prerender(self)
    -- UI keeps rendering while paused; OnTick alone does not cover that case.
    Radio.tick()
    local selected = self:isSelected()
    self.useButton:setTitle(selected and "Volver a la emisora anterior" or "Sintonizar Pear FM")
    self.pauseButton:setTitle(Radio.paused and "Seguir" or "Pausa")
    local powered = selected and self.deviceData and self.deviceData:getIsTurnedOn()
    self.pauseButton:setEnable(powered == true)
    self.nextButton:setEnable(powered == true and not Radio.paused and getGameSpeed() > 0)
    self.previousButton:setEnable(powered == true and not Radio.paused and getGameSpeed() > 0)

    local status = Radio.status
    local hint = Radio.frequency and string.format("Pear FM - %.1f MHz", Radio.frequency / 1000)
        or "No hay frecuencia FM libre para Pear."
    if isClient() then hint = "MVP disponible solo en singleplayer."
    elseif selected and not powered then hint = "Enciende la radio del coche."
    elseif selected and getGameSpeed() == 0 then hint = "Despausa la partida para reproducir."
    elseif selected and Radio.paused then hint = "Pausa desde el coche."
    end
    local lines = {hint, Radio.fileError or status.message or "Puente sin conexion. Ejecuta Iniciar-Puente.cmd.",
        status.title or "Sin cancion", status.artist or ""}
    self:setStencilRect(8, self.textY, self.width - 16, self.lineHeight * 4)
    for i, line in ipairs(lines) do
        self:drawText(line, 10, self.textY + (i - 1) * self.lineHeight, 0.85, 0.95, 0.85, 1, UIFont.Small)
    end
    self:clearStencilRect()
end

-- Add the real preset before vanilla builds its channel dropdown and info panel.
local originalReadFromObject = ISRadioWindow.readFromObject
function ISRadioWindow:readFromObject(player, device)
    if not isClient() and not isServer() and player and player:getPlayerNum() == 0
        and device and instanceof(device, "VehiclePart") and player:getVehicle() == device:getVehicle() then
        local data = device:getDeviceData()
        if data then Radio.ensurePreset(data) end
    end
    originalReadFromObject(self, player, device)
end

-- Preserve vanilla and other mods' modules.
local originalCreateChildren = ISRadioWindow.createChildren
function ISRadioWindow:createChildren()
    originalCreateChildren(self)
    if not isClient() and not isServer() then
        self:addModule(RWMPearCarRadio:new(0, 0, self.width, 0), "Pear Car Radio", true)
    end
end

Events.OnTick.Add(Radio.tick)
Events.OnGameStart.Add(function()
    Radio.session = tostring(getTimestampMs())
    Radio.frame = 0
    Radio.actionId = 0
    Radio.action = "none"
    Radio.status = {}
    Radio.previousChannels = {}
    Radio.frequency = nil
    Radio.registerStation()
    Radio.stop()
end)
if Events.OnMainMenuEnter then Events.OnMainMenuEnter.Add(Radio.stop) end

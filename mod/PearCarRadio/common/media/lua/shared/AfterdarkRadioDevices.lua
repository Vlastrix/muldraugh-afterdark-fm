require "AfterdarkGameProtocol"
AfterdarkRadioDevices = {}
local D, P = AfterdarkRadioDevices, AfterdarkGameProtocol
D.name = "Muldraugh Afterdark FM"

function D.station(frequency)
    local radio = getZomboidRadio()
    if not radio then return nil end
    if frequency then
        if D.frequency==frequency and radio:getChannelName(frequency)==D.name then return frequency end
        D.frequency = frequency
        radio:addChannelName(D.name, frequency, "Radio", false)
    elseif not D.frequency then
        for offset = 0, 19 do
            local candidate = 88000 + ((6 + offset) % 20) * 1000 + 600
            local name = radio:getChannelName(candidate)
            if not name or name == D.name then
                D.frequency = candidate
                radio:addChannelName(D.name, candidate, "Radio", false)
                break
            end
        end
    end
    return D.frequency
end

function D.reference(object)
    if instanceof(object, "VehiclePart") then
        return {kind="car", vehicle=object:getVehicle():getId()}
    elseif instanceof(object, "IsoWaveSignal") and object:getSquare() then
        return {kind="world", x=object:getX(), y=object:getY(), z=object:getZ(), index=object:getObjectIndex()}
    end
end

function D.key(ref)
    if type(ref) ~= "table" then return nil end
    if ref.kind == "car" and P.integer(ref.vehicle,0,32767) then return "car_" .. tostring(ref.vehicle) end
    if ref.kind == "world" and P.integer(ref.x,0,1000000) and P.integer(ref.y,0,1000000)
        and P.integer(ref.z,-32,32) and P.integer(ref.index,0,1000) then
        return string.format("world_%d_%d_%d_%d", ref.x, ref.y, ref.z, ref.index)
    end
end

function D.resolve(ref)
    if not D.key(ref) then return nil end
    local object, vehicle
    if ref.kind == "car" then
        vehicle = getVehicleById(ref.vehicle)
        if not vehicle or not vehicle:getSquare() then return nil end
        object = vehicle:getPartById("Radio")
        if not object or not object:getInventoryItem() then return nil end
    else
        local square = getCell():getGridSquare(ref.x,ref.y,ref.z)
        local objects = square and square:getObjects()
        if not objects or ref.index >= objects:size() then return nil end
        object = objects:get(ref.index)
        if not instanceof(object,"IsoWaveSignal") then return nil end
    end
    local data = object:getDeviceData()
    if not data or data:getIsTelevision() then return nil end
    return {object=object, vehicle=vehicle, data=data, x=object:getX(), y=object:getY(), z=object:getZ()}
end

function D.active(source)
    return D.frequency and source.data:getChannel() == D.frequency
        and source.data:getIsTurnedOn() and source.data:canBePoweredHere()
end

function D.canControl(player, source)
    if player:isDead() then return false end
    if source.vehicle then return player:getVehicle() == source.vehicle end
    local dx, dy = player:getX()-source.x, player:getY()-source.y
    return math.floor(player:getZ()) == math.floor(source.z) and dx*dx+dy*dy <= 4
end

function D.gain(player, source)
    if player:isDead() or not D.active(source) then return 0 end
    local volume = math.max(0,math.min(1,source.data:getDeviceVolume()))
    if source.vehicle and player:getVehicle() == source.vehicle then return volume end
    if math.floor(player:getZ()) ~= math.floor(source.z) then return 0 end
    local dx, dy = player:getX()-source.x, player:getY()-source.y
    local distance = math.sqrt(dx*dx+dy*dy)
    return volume * math.max(0,1-distance/math.max(1,35*volume))^2
end

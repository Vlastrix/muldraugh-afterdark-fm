-- Experimental transport only. No vehicle integration or public MP support yet.
AfterdarkGameProtocol = {}
local P = AfterdarkGameProtocol
P.module = "AfterdarkGameLab"
P.slots = 16
P.maxPayload = 1000
P.maxSequence = 2147483647

function P.integer(value, minimum, maximum)
    return type(value) == "number" and value == value and value >= minimum
        and value <= maximum and value == math.floor(value)
end

function P.token(value)
    return type(value) == "string" and #value == 32 and value:match("^[a-f0-9]+$") ~= nil
end

function P.room(value)
    return type(value) == "string" and #value > 0 and #value <= 80
        and value:match("^[%w_%-]+$") ~= nil
end

function P.payload(value)
    return type(value) == "string" and #value >= 12 and #value <= P.maxPayload
        and #value % 4 == 0 and value:match("^[A-Za-z0-9+/=]+$") ~= nil
end

local function encode(value)
    return (tostring(value):gsub("[^%w%-%._~]", function(char)
        return string.format("%%%02X", string.byte(char))
    end))
end

local function decode(value)
    return (value:gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end))
end

function P.read(name)
    local file = getFileReader(name, false)
    if not file then return nil end
    local values, count, last = {}, 0, nil
    local line = file:readLine()
    while line and count < 20 do
        count = count + 1
        if #line > 3000 then file:close(); return nil end
        local key, value = line:match("^([a-z_]+)=(.*)$")
        if not key or values[key] then file:close(); return nil end
        values[key] = decode(value)
        last = key
        line = file:readLine()
    end
    file:close()
    if line or last ~= "commit" or not values.serial or values.serial ~= values.commit then return nil end
    return values
end

function P.write(name, values)
    local file = getFileWriter(name, true, false)
    if not file then return false end
    for key, value in pairs(values) do file:write(key .. "=" .. encode(value) .. "\n") end
    file:write("commit=" .. encode(values.serial) .. "\n")
    file:close()
    return true
end

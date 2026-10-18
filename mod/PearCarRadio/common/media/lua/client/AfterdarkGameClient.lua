require "AfterdarkGameProtocol"
if not isClient() then return end
local P = AfterdarkGameProtocol
local control, status = nil, {status="connecting", room="", owner=""}
local lastPoll, lastHello, lastStatus = 0, 0, 0
local txSequence, rxSequence, stateSerial = -1, -1, 0
local txCount, rxCount, dropped, errors = 0, 0, 0, 0
local confirmed, probeSequence = 0, -1
local lastServer, rtt = 0, 0

local function leave()
    if control then sendClientCommand(P.module, "leave", {client=control.client}) end
    control = nil
    status = {status="connecting", room="", owner=""}
    txSequence, rxSequence, lastHello = -1, -1, 0
    txCount, rxCount, dropped, errors, confirmed, probeSequence = 0, 0, 0, 0, 0, -1
end

local function onServer(module, command, args)
    if module ~= P.module or type(args) ~= "table" or not control or args.client ~= control.client then return end
    local now = getTimestampMs()
    if command == "state" then
        local allowed = {waiting=true, sending=true, listening=true, busy=true, full=true}
        if not allowed[args.status] or type(args.room) ~= "string" or (args.room ~= "" and not P.room(args.room)) then return end
        if args.room ~= status.room then txSequence, rxSequence, probeSequence = -1, -1, -1 end
        status = {status=args.status, room=args.room, owner=type(args.owner)=="string" and args.owner:sub(1,80) or "",
            rejected=P.integer(args.rejected,0,P.maxSequence) and args.rejected or 0,
            listeners=P.integer(args.listeners,0,8) and args.listeners or 0}
        if P.integer(args.echo,1,9007199254740991) and now >= args.echo and now - args.echo < 5000 then rtt = now - args.echo end
        lastServer = now
        return
    end
    if command == "probe" and control.role == "tone" and args.room == status.room
        and P.integer(args.sequence,0,P.maxSequence) and args.sequence > probeSequence and P.payload(args.payload) then
        local original = P.read("AfterdarkGame.tx." .. tostring(args.sequence % P.slots) .. ".txt")
        if original and original.client == control.client and original.room == args.room
            and original.serial == tostring(args.sequence) and original.payload == args.payload then
            confirmed = confirmed + 1
            probeSequence = args.sequence
        end
        return
    end
    if command ~= "audio" or control.role ~= "listen" or status.status ~= "listening"
        or args.room ~= status.room or not P.integer(args.sequence,0,P.maxSequence)
        or args.sequence <= rxSequence or not P.payload(args.payload) then return end
    if rxSequence >= 0 then dropped = dropped + math.max(0, args.sequence - rxSequence - 1) end
    rxSequence = args.sequence
    local values = {serial=rxSequence, client=control.client, room=args.room, payload=args.payload, timestamp=now}
    local ok = P.write("AfterdarkGame.rx." .. tostring(rxSequence % P.slots) .. ".txt", values)
    if ok then ok = P.write("AfterdarkGame.rx.txt", {serial=rxSequence, client=control.client, room=args.room, timestamp=now}) end
    if ok then rxCount = rxCount + 1 else errors = errors + 1 end
end

local function tick()
    local now = getTimestampMs()
    if now >= lastPoll and now - lastPoll < 40 then return end
    lastPoll = now
    local incoming = P.read("AfterdarkGame.control.txt")
    local timestamp = incoming and tonumber(incoming.timestamp) or 0
    if not incoming or not P.token(incoming.client) or not P.integer(timestamp,0,9007199254740991)
        or math.abs(now - timestamp) > 2000 or incoming.role == "stop" then
        if control then leave() end
        return
    end
    if incoming.role ~= "listen" and incoming.role ~= "share" and incoming.role ~= "tone" then return end
    if control and (incoming.client ~= control.client or incoming.role ~= control.role) then leave() end
    control = incoming
    if now < lastHello or now - lastHello >= 1000 then
        lastHello = now
        sendClientCommand(P.module, "hello", {client=control.client, role=control.role, echo=now})
    end
    if lastServer == 0 or now - lastServer > 3000 then status = {status="connecting", room="", owner=""} end
    if status.status == "sending" then
        local manifest = P.read("AfterdarkGame.tx.txt")
        local latest = manifest and tonumber(manifest.serial) or -1
        if manifest and manifest.client == control.client and manifest.room == status.room
            and P.integer(latest,0,P.maxSequence) then
            local start = math.max(txSequence + 1, latest - 1)
            if start > txSequence + 1 then dropped = dropped + start - txSequence - 1 end
            for sequence = start, latest do
                local packet = P.read("AfterdarkGame.tx." .. tostring(sequence % P.slots) .. ".txt")
                local written = packet and tonumber(packet.timestamp) or 0
                if packet and packet.client == control.client and packet.room == status.room
                    and packet.serial == tostring(sequence) and math.abs(now-written) <= 300 and P.payload(packet.payload) then
                    sendClientCommand(P.module, "audio", {client=control.client, room=status.room,
                        sequence=sequence, payload=packet.payload})
                    txSequence = sequence
                    txCount = txCount + 1
                end
            end
        end
    end
    if now < lastStatus or now - lastStatus >= 200 then
        lastStatus = now
        stateSerial = stateSerial + 1
        if not P.write("AfterdarkGame.status.txt", {serial=stateSerial, client=control.client,
            room=status.room, status=status.status, owner=status.owner, timestamp=now,
            sent=txCount, received=rxCount, dropped=dropped, errors=errors, rtt=rtt,
            rejected=status.rejected or 0, listeners=status.listeners or 0, confirmed=confirmed}) then errors = errors + 1 end
    end
end

Events.OnServerCommand.Add(onServer)
Events.OnTick.Add(tick)
Events.OnMainMenuEnter.Add(leave)

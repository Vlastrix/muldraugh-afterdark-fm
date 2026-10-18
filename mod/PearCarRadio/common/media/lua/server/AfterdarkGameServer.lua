require "AfterdarkGameProtocol"
if not isServer() then return end
local P = AfterdarkGameProtocol
local peers, owner, room = {}, nil, nil
local generation, lastSweep = 0, 0

local function clearOwner()
    owner, room = nil, nil
end

local function countListeners()
    local count = 0
    for _, peer in pairs(peers) do if peer.role == "listen" then count = count + 1 end end
    return count
end

local function state(peer, echo)
    local status = "waiting"
    if peer == owner then status = "sending"
    elseif peer.role ~= "listen" then status = "busy"
    elseif owner then status = "listening" end
    sendServerCommand(peer.player, P.module, "state", {
        client = peer.client, room = room or "", status = status,
        owner = owner and owner.player:getUsername() or "", echo = echo or 0,
        rejected = peer.rejected, listeners = countListeners(),
    })
end

local function broadcastState()
    for _, peer in pairs(peers) do state(peer) end
end

local function removePeer(id)
    if peers[id] == owner then clearOwner() end
    peers[id] = nil
end

local function onCommand(module, command, player, args)
    if module ~= P.module or not player or type(args) ~= "table" or not P.token(args.client) then return end
    local now = getTimestampMs()
    local id = player:getOnlineID()
    if not P.integer(id, 0, 32767) then return end
    local peer = peers[id]
    if command == "leave" then
        if peer and peer.client == args.client then removePeer(id); broadcastState() end
        return
    end
    if command == "hello" then
        if args.role ~= "listen" and args.role ~= "share" and args.role ~= "tone" then return end
        if not P.integer(args.echo, 0, 9007199254740991) then return end
        if peer and now - peer.lastHello < 500 then return end
        if peer and (peer.client ~= args.client or peer.role ~= args.role) then removePeer(id); peer = nil end
        if not peer then
            local count = 0
            for _ in pairs(peers) do count = count + 1 end
            if count >= 9 or (args.role == "listen" and countListeners() >= 8) then
                sendServerCommand(player, P.module, "state", {client=args.client, status="full", room="", echo=args.echo})
                return
            end
            peer = {player=player, client=args.client, role=args.role, lastSequence=-1, rejected=0,
                window=now, batches=0, lastHello=now}
            peers[id] = peer
        end
        peer.player, peer.lastHello = player, now
        if peer.role ~= "listen" and not owner then
            generation = generation + 1
            room = string.format("%.0f", now) .. "_" .. tostring(generation)
            owner = peer
            peer.lastSequence = -1
            broadcastState()
        end
        state(peer, args.echo)
        return
    end
    if command ~= "audio" or not peer or peer ~= owner or peer.client ~= args.client
        or now - peer.lastHello > 3000 or args.room ~= room then return end
    if not P.integer(args.sequence, 0, P.maxSequence) or args.sequence <= peer.lastSequence
        or not P.payload(args.payload) then peer.rejected = peer.rejected + 1; return end
    if now < peer.window or now - peer.window >= 1000 then peer.window = now; peer.batches = 0 end
    if peer.batches >= 30 then peer.rejected = peer.rejected + 1; return end
    peer.batches = peer.batches + 1
    peer.lastSequence = args.sequence
    for _, listener in pairs(peers) do
        if listener.role == "listen" and now - listener.lastHello <= 3000 then
            sendServerCommand(listener.player, P.module, "audio", {
                client=listener.client, room=room, sequence=args.sequence, payload=args.payload,
            })
        end
    end
    -- Synthetic mode also verifies a round trip with one player; never monitor Pear twice.
    if peer.role == "tone" then
        sendServerCommand(peer.player, P.module, "probe", {
            client=peer.client, room=room, sequence=args.sequence, payload=args.payload,
        })
    end
end

local function tick()
    local now = getTimestampMs()
    if now >= lastSweep and now - lastSweep < 500 then return end
    lastSweep = now
    local online = {}
    local players = getOnlinePlayers()
    for i = 0, players:size() - 1 do online[players:get(i):getOnlineID()] = true end
    local changed = false
    for id, peer in pairs(peers) do
        if not online[id] or now < peer.lastHello or now - peer.lastHello > 3000 then
            removePeer(id); changed = true
        end
    end
    if changed then broadcastState() end
end

Events.OnClientCommand.Add(onCommand)
Events.OnTick.Add(tick)

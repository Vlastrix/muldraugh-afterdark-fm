require "AfterdarkRadioDevices"
if not isServer() then return end
AfterdarkRadioServer = {}
local R, D, P = AfterdarkRadioServer, AfterdarkRadioDevices, AfterdarkGameProtocol
local peers, sessions = {}, {}
local generation, lastSweep, lastNoise = 0, 0, 0

local function removeSessions(peer)
    for key, session in pairs(sessions) do
        if session.owner == peer then sessions[key] = nil end
    end
end

local function owned(peer)
    for _, session in pairs(sessions) do if session.owner == peer then return session end end
end

local function selectSource(peer)
    local mine = owned(peer)
    if mine then return mine, D.gain(peer.player,mine.source) end
    local selected, gain, priority = nil, 0, false
    for _, session in pairs(sessions) do
        local value = D.gain(peer.player,session.source)
        local occupant = session.source.vehicle ~= nil and peer.player:getVehicle() == session.source.vehicle
        if value > 0 and (not selected or (occupant and not priority) or (occupant == priority and value > gain)) then
            selected, gain, priority = session, value, occupant == true
        end
    end
    return selected, gain
end

local function state(peer, echo)
    local session, gain = selectSource(peer)
    peer.follow = session
    sendServerCommand(peer.player,P.module,"state",{
        client=peer.client, status=session and (session.owner == peer and "sending" or "listening") or "waiting",
        room=session and session.room or "", owner=session and session.owner.player:getUsername() or "",
        echo=echo or 0, rejected=peer.rejected, listeners=0,
    })
    local command = session and session.owner == peer and session.commands[1]
    sendServerCommand(peer.player,P.module,"radio_state",{
        client=peer.client, room=session and session.room or "", key=session and session.key or "",
        owner=session and session.owner.player:getUsername() or "", gain=gain or 0,
        paused=session and session.paused or false, frequency=D.station() or 0, ready=peer.ready==true,
        command_id=command and command.id or 0, action=command and command.action or "none",
        title=session and session.title or "", artist=session and session.artist or "",
        message=peer.message or "", source=session and session.ref or nil,
    })
    peer.message = nil
end

local function broadcast()
    for _, peer in pairs(peers) do state(peer) end
end

function R.onCommand(command, player, args)
    local id, now = player:getOnlineID(), getTimestampMs()
    local peer = peers[id]
    if command == "hello" and args.role == "radio" then
        if not P.integer(args.echo,0,9007199254740991) then return true end
        if peer and now-peer.lastHello < 500 then return true end
        if peer and peer.client ~= args.client then removeSessions(peer); peers[id]=nil; peer=nil end
        if not peer then
            local count = 0
            for _ in pairs(peers) do count=count+1 end
            if count >= 9 then
                sendServerCommand(player,P.module,"state",{client=args.client,status="full",room="",echo=args.echo})
                return true
            end
            peer = {player=player,client=args.client,lastHello=now,lastAction=-1,lastRequest=0,rejected=0}
            peers[id] = peer
        end
        peer.player, peer.lastHello, peer.ready = player, now, args.ready == true
        local session = owned(peer)
        if session and not peer.ready then removeSessions(peer); session=nil end
        if session and args.report_room == session.room then
            if args.playing == true then session.lastPlaying=now else session.lastPlaying=0 end
            session.title = type(args.title)=="string" and args.title:sub(1,240) or ""
            session.artist = type(args.artist)=="string" and args.artist:sub(1,160) or ""
            local pending = session.commands[1]
            if pending and args.command_ack == pending.id then table.remove(session.commands,1) end
        end
        state(peer,args.echo)
        return true
    end
    if not peer then return command == "radio_use" or command == "radio_control" end
    if peer.client ~= args.client then return true end
    if command == "leave" or (command == "hello" and args.role ~= "radio") then
        removeSessions(peer); peers[id]=nil; broadcast()
        return command == "leave"
    end
    if now-peer.lastHello > 3000 then return true end
    if command == "radio_use" or command == "radio_control" then
        if not P.integer(args.request,0,P.maxSequence) or args.request <= peer.lastAction then return true end
        peer.lastAction = args.request
        if now-peer.lastRequest < 300 then return true end
        peer.lastRequest=now
        local ref = args.source
        -- Check proximity before resolving a caller-supplied world square.
        if type(ref)=="table" and ref.kind=="world" then
            if not D.key(ref) or math.abs(player:getX()-ref.x)>3 or math.abs(player:getY()-ref.y)>3
                or math.floor(player:getZ())~=ref.z then return true end
        end
        local source = D.resolve(ref)
        if not source or not D.canControl(player,source) or not D.active(source) then return true end
        local key = D.key(ref)
        if command == "radio_use" then
            if not peer.ready then peer.message="Enable Share capability in the Radio connector first."; state(peer); return true end
            local count=0
            for _ in pairs(sessions) do count=count+1 end
            if not sessions[key] and not owned(peer) and count>=4 then return true end
            removeSessions(peer)
            generation=generation+1
            sessions[key]={key=key,ref=ref,source=source,object=source.object,owner=peer,
                room=string.format("%.0f_radio_%d",now,generation), paused=false,commands={},actionId=0,
                lastSequence=-1,window=now,batches=0,lastAudio=0,lastPlaying=0,title="",artist=""}
            broadcast()
        else
            local session=sessions[key]
            if not session or args.room~=session.room then return true end
            local action=args.action
            if action=="release" and session.owner==peer then sessions[key]=nil; broadcast(); return true end
            if action~="previous" and action~="next" and action~="pause" and action~="play" then return true end
            if #session.commands>=8 then return true end
            session.actionId=session.actionId+1
            table.insert(session.commands,{id=session.actionId,action=action})
            if action=="pause" then session.paused=true elseif action=="play" then session.paused=false end
            broadcast()
        end
        return true
    end
    if command == "audio" then
        local session=owned(peer)
        if not session or args.room~=session.room or session.paused or not D.active(session.source) then return true end
        if not P.integer(args.sequence,0,P.maxSequence) or args.sequence<=session.lastSequence or not P.payload(args.payload) then
            peer.rejected=peer.rejected+1; return true
        end
        if now<session.window or now-session.window>=1000 then session.window=now; session.batches=0 end
        if session.batches>=30 then peer.rejected=peer.rejected+1; return true end
        session.batches=session.batches+1
        session.lastSequence, session.lastAudio=args.sequence,now
        local count=0
        for _, listener in pairs(peers) do
            if listener~=peer and listener.follow==session and now-listener.lastHello<=3000
                and D.gain(listener.player,session.source)>0 and count<8 then
                sendServerCommand(listener.player,P.module,"audio",{client=listener.client,room=session.room,
                    sequence=args.sequence,payload=args.payload})
                count=count+1
            end
        end
        return true
    end
    return true
end

local function tick()
    local now=getTimestampMs()
    if now>=lastSweep and now-lastSweep<250 then return end
    lastSweep=now
    local online={}
    local players=getOnlinePlayers()
    for i=0,players:size()-1 do online[players:get(i):getOnlineID()]=true end
    for id,peer in pairs(peers) do
        if not online[id] or peer.player:isDead() or now<peer.lastHello or now-peer.lastHello>3000 then
            removeSessions(peer); peers[id]=nil
        end
    end
    for key,session in pairs(sessions) do
        local source=D.resolve(session.ref)
        if not source or source.object~=session.object or not D.active(source) then sessions[key]=nil
        else
            session.source=source
            if now-lastNoise>=1000 and not session.paused and now-session.lastAudio<500
                and now-session.lastPlaying<2000 and source.data:getDeviceVolume()>0 then
                local radius=math.max(1,math.floor(35*source.data:getDeviceVolume()))
                addSound(session.owner.player,math.floor(source.x),math.floor(source.y),math.floor(source.z),radius,radius)
            end
        end
    end
    if now-lastNoise>=1000 then lastNoise=now end
    broadcast()
end
Events.OnTick.Add(tick)

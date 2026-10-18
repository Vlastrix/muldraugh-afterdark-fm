require "AfterdarkRadioDevices"
if not isClient() then return end
AfterdarkRadioClient = {state={},request=0}
local R,D,P=AfterdarkRadioClient,AfterdarkRadioDevices,AfterdarkGameProtocol
local lastState=0
local muted={}

function R.clear()
    R.control=nil
    R.state={}
    for device in pairs(muted) do pcall(function() device:cleanSoundsAndEmitter() end) end
    muted={}
end

function R.hello(hello,control)
    hello.ready=control.ready=="1"
    hello.report_room=control.report_room or ""
    hello.playing=control.playing=="1"
    hello.title=(control.title or ""):sub(1,240)
    hello.artist=(control.artist or ""):sub(1,160)
    hello.command_ack=tonumber(control.command_ack) or 0
end

function R.onServer(command,args)
    if command~="radio_state" or type(args.room)~="string" or (args.room~="" and not P.room(args.room)) then return end
    if not P.integer(args.frequency,88000,108000) then return end
    D.station(args.frequency)
    R.state=args
    lastState=getTimestampMs()
end

function R.writeState(serial,status)
    local fresh=getTimestampMs()-lastState<=1000
    local state=fresh and R.state or {}
    P.write("AfterdarkRadio.info.txt",{serial=serial,client=R.control.client,room=state.room or "",
        owning=status.status=="sending" and fresh and "1" or "0",paused=state.paused and "1" or "0",
        gain=tonumber(state.gain) or 0, command_id=tonumber(state.command_id) or 0,action=state.action or "none",
        volume=tonumber(state.volume) or 0,
        title=state.title or "",artist=state.artist or "",owner=state.owner or "",message=state.message or ""})
end

function R.send(command,object,action)
    if not R.control or R.control.role~="radio" then return end
    local ref=D.reference(object)
    if not ref then return end
    R.request=R.request+1
    sendClientCommand(P.module,command,{client=R.control.client,source=ref,request=R.request,
        room=R.state.room or "",action=action})
end

local function tick()
    local keep={}
    if R.control then
        local source=R.state.source and D.resolve(R.state.source)
        if source and D.active(source) then keep[source.data]=true end
        local windows=ISRadioWindow and ISRadioWindow.instancesIso
        local window=windows and windows[0]
        if window and window.deviceData and window.deviceData:getChannel()==D.frequency then keep[window.deviceData]=true end
    end
    for device in pairs(muted) do
        if not keep[device] then pcall(function() device:cleanSoundsAndEmitter() end) end
    end
    for device in pairs(keep) do
        pcall(function()
            device:doReceiveSignal(0)
            local emitter=device:getEmitter()
            if emitter then emitter:setVolumeAll(0) end
        end)
    end
    muted=keep
end
Events.OnTick.Add(tick)
require "AfterdarkRadioUI"

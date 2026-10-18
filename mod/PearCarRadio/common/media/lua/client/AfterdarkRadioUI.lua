if not isClient() then return end
require "RadioCom/ISRadioWindow"
require "RadioCom/RadioWindowModules/RWMPanel"
require "RadioCom/RadioWindowModules/RWMChannel"
require "ISUI/ISButton"
require "RadioCom/ISRadioAction"
require "TimedActions/ISTimedActionQueue"
local R,D=AfterdarkRadioClient,AfterdarkRadioDevices
RWMAfterdarkRadio=RWMPanel:derive("RWMAfterdarkRadio")

function RWMAfterdarkRadio:createChildren()
    self.lineHeight=getTextManager():getFontHeight(UIFont.Small)+4
    local height=self.lineHeight+8
    self:setHeight(height*4+self.lineHeight*4+30)
    local function button(x,y,width,title,callback)
        local item=ISButton:new(x,y,width,height,title,self,callback)
        item:initialise(); self:addChild(item)
        return item
    end
    self.tune=button(10,8,self.width-20,"Tune to Afterdark FM",self.onTune)
    self.use=button(10,height+12,self.width-20,"Use my Pear",self.onUse)
    local width=(self.width-28)/3
    self.previous=button(10,height*2+16,width,"Previous",self.onPrevious)
    self.pause=button(14+width,height*2+16,width,"Pause",self.onPause)
    self.next=button(18+width*2,height*2+16,width,"Next",self.onNext)
    self.release=button(10,height*3+20,self.width-20,"Stop sharing",self.onRelease)
    self.textY=height*4+26
end

function RWMAfterdarkRadio:readFromObject(player,device,data,kind)
    RWMPanel.readFromObject(self,player,device,data,kind)
    return player:getPlayerNum()==0 and not data:getIsTelevision() and (kind=="VehiclePart" or kind=="IsoObject")
end

function RWMAfterdarkRadio:onTune()
    if not D.frequency or not self:doWalkTo() then return end
    if self.deviceData:getChannel()~=D.frequency then
        ISTimedActionQueue.add(ISRadioAction:new("SetChannel",self.player,self.device,D.frequency))
    end
    R.refreshWindow(self.player,self.device)
end
function RWMAfterdarkRadio:onUse()
    if self:doWalkTo() then R.send("radio_use",self.device) end
end
function RWMAfterdarkRadio:onPrevious() R.send("radio_control",self.device,"previous") end
function RWMAfterdarkRadio:onNext() R.send("radio_control",self.device,"next") end
function RWMAfterdarkRadio:onPause() R.send("radio_control",self.device,R.state.paused and "play" or "pause") end
function RWMAfterdarkRadio:onRelease() R.send("radio_control",self.device,"release") end

function RWMAfterdarkRadio:prerender()
    RWMPanel.prerender(self)
    local key=D.key(D.reference(self.device))
    local source=D.resolve(D.reference(self.device))
    local active=source and D.active(source) and D.canControl(self.player,source)
    local connected=R.control and getTimestampMs()-tonumber(R.control.timestamp)<=2000
    local selected=R.state.key==key and R.state.room~=""
    local tuned=self.deviceData and self.deviceData:getChannel()==D.frequency
    self.tune:setTitle(tuned and "Tuned to Afterdark FM" or "Tune to Afterdark FM")
    self.tune:setEnable(connected and D.frequency~=nil and not tuned and self.deviceData:getIsTurnedOn() or false)
    self.use:setEnable(connected and active and R.state.ready==true or false)
    for _,button in ipairs({self.previous,self.next,self.pause}) do button:setEnable(connected and active and selected or false) end
    self.release:setEnable(connected and active and selected and R.state.owner==self.player:getUsername() or false)
    self.pause:setTitle(R.state.paused and "Resume" or "Pause")
    local lines={connected and ("Afterdark FM - "..string.format("%.1f MHz",(D.frequency or 94600)/1000)) or "Open the Connector in Radio mode.",
        selected and ("Owner: "..(R.state.owner or "")) or "Tune in, then press Use my Pear.",
        selected and (R.state.title or "") or "Listeners do not need Pear.",
        R.state.message~="" and R.state.message or (selected and R.state.artist or "") or ""}
    self:setStencilRect(8,self.textY,self.width-16,self.lineHeight*4)
    for i,line in ipairs(lines) do self:drawText(line,10,self.textY+(i-1)*self.lineHeight,0.85,0.95,0.85,1,UIFont.Small) end
    self:clearStencilRect()
end

local originalRead=ISRadioWindow.readFromObject
function ISRadioWindow:readFromObject(player,device)
    if player and device and D.frequency and (instanceof(device,"VehiclePart") or instanceof(device,"IsoWaveSignal")) then
        local data=device:getDeviceData()
        if data and not data:getIsTelevision() and D.frequency>=data:getMinChannelRange() and D.frequency<=data:getMaxChannelRange() then
            local presets=data:getDevicePresets()
            local entries=presets and presets:getPresets()
            local found=false
            if entries then
                for i=0,entries:size()-1 do if entries:get(i):getFrequency()==D.frequency then found=true end end
                if not found and entries:size()<presets:getMaxPresets() then
                    presets:addPreset(D.name,D.frequency); data:transmitPresets()
                end
            end
        end
    end
    originalRead(self,player,device)
end

function R.refreshWindow(player,device)
    local windows=ISRadioWindow.instancesIso
    local window=windows and windows[player:getPlayerNum()]
    if window and window.device==device then window:readFromObject(player,device) end
end

-- A timed action or remote player can change the channel after the button returns.
local function refreshTuning()
    local windows=ISRadioWindow.instancesIso
    local window=windows and windows[0]
    if not window or not window.deviceData or not window.player or not window.device then return end
    local channel=window.deviceData:getChannel()
    if window.afterdarkChannel~=channel or window.afterdarkFrequency~=D.frequency then
        window.afterdarkChannel=channel
        window.afterdarkFrequency=D.frequency
        R.refreshWindow(window.player,window.device)
    end
end
Events.OnTick.Add(refreshTuning)
local originalCreate=ISRadioWindow.createChildren
function ISRadioWindow:createChildren()
    originalCreate(self)
    self:addModule(RWMAfterdarkRadio:new(0,0,self.width,0),D.name,true)
end
local originalCombo=RWMChannel.addComboOption
function RWMChannel:addComboOption(frequency,name)
    if frequency==D.frequency and name==D.name then
        self.comboBox:addOption(string.format("%.1f MHz Afterdark FM",frequency/1000))
    else originalCombo(self,frequency,name) end
end

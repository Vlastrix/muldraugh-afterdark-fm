# Muldraugh Afterdark FM

Play the **song or playlist already open in Pear Desktop** through **94.46 MHz Afterdark FM** on your Project Zomboid car radio. Audio plays in Pear; the mod does not download or retransmit music. Version **0.4.2**, experimental, singleplayer only. Requires Build 42.20 or later; developed against Build 42.21 and Pear 3.12.0.

## Setup

1. Open Pear Desktop / YouTube Music, select a song or playlist and verify playback.
2. Enable Pear's **API Server** plugin. Use hostname `127.0.0.1`, port `26538`, and **Auth at first** authentication. No router port forwarding is required. API documentation is available at <http://127.0.0.1:26538/swagger> while enabled.
3. Close Zomboid and run `powershell -ExecutionPolicy Bypass -File .\Install-Mod.ps1`. This copies the mod into your local mods directory; it does not edit game files or enable mods in a save.
4. Run **Start-Bridge.cmd**. Requires Python 3.9 or later, with no extra packages to play. Authorize **PZPearCarRadio** when prompted and keep the bridge open. Never share tokens or credentials.
5. Start Zomboid and enable **Muldraugh Afterdark FM**. For an existing save, use **Load → More → Choose mods**. A test save is recommended.
6. Enter a car with an installed radio and a charged battery. Open its radio from the vehicle menu (`V`) and switch it on. Select **94.46 MHz Afterdark FM** under **Channel**, then press **Tune in**. The panel also has a **Tune to Afterdark FM** shortcut.
7. Use the normal radio volume control and **Previous / Pause / Next**. Unpause the game to play music.

Stop the bridge with **Ctrl+C**. Forcefully terminating its process can prevent the final pause command.

## Radio behavior

The frequency is saved with the radio. Switching stations pauses Pear and restores normal radio audio. **Return to previous station** switches back directly.

**Music continues after you leave the car** while its radio is powered, switched on and tuned to Afterdark FM. Outside volume fades with distance: at full volume, the approximate range is 35 tiles; lower volume reduces the range. Inside, the selected volume is preserved. Walls, windows and stereo direction are not simulated.

Beyond hearing range, the song advances silently while the car remains loaded. If the game unloads or removes it, playback pauses and the source is forgotten until you enter the car again. Only the last car used during the session is tracked. Entering another car changes the source; radios are not mixed. Loading a save on foot does not discover nearby cars automatically.

Death, leaving the game or losing the mod heartbeat pauses controlled playback. Heartbeats expire after three seconds. The bridge restores Pear's previous numeric volume when releasing control, but not its previous song, queue or playback state. It never changes Windows volume.

Pausing directly in Pear is respected. Use **Pause**, then **Resume** in the car to restart playback. Display updates can take about a second plus loading time. Escape-menu pause behavior still needs refinement and can differ from the game speed controls.

## Frequency and world noise

Afterdark FM prefers **94.46 MHz**. If occupied, it picks another free frequency ending in `.46`, such as 95.46 MHz. The dropdown displays both decimal places. Other stations are not overwritten.

A preset is added when you open the radio. If all slots are occupied, existing presets are preserved and the panel shortcut still works. Free a slot and reopen the radio to add the dropdown entry.

The tracked radio receives a local signal to prevent new static text such as `<wzzt>`. Other radios and character speech are unchanged. The mod avoids `ChatElement`, which is not exposed to Lua in Build 42.21. Unsupported signal updates disable only this optional feature; playback and controls continue. Existing text expires normally. This signal also uses the engine's native radio noise behavior.

**Music attracts zombies** by default; configure it in **Options → Mods → Muldraugh Afterdark FM**. Additional noise is generated at the car while Pear confirms playback, reaching roughly 35 tiles at full volume. Walking away reduces what you hear, not what zombies hear at the car. This adds to normal vehicle/radio noise and does not guarantee a zombie count. Muting Pear manually does not automatically change world noise; use the car's volume or pause controls.

Original radio voices and static audio are muted on Afterdark FM. This is configurable in the mod options; switching stations restores the original emitter.

## Limitations

- Singleplayer, local player 0 only. Multiplayer and split-screen are not supported yet.
- Select music **in Pear**. Loading links from the game is pending; upstream playlist API work is tracked in [Pear #4615](https://github.com/pear-devs/pear-desktop/pull/4615).
- Pear and the bridge must stay open. Workshop alone will not launch the bridge.
- Playback, content availability and account access depend on Pear. The mod never receives your Google password.

## Updating

Install the current version with **Install-Mod.ps1** and restart Zomboid. Restart **Start-Bridge.cmd** when the bridge changes too.

During development, the project supports the current version without save migrations or backward-compatibility layers. Breaking changes may require a new world with the mod enabled; the update instructions will say when to create one. Old presets and saved data are not upgraded automatically.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Mod missing | Restart Zomboid, use Build 42.20+ and enable the mod for the save too |
| Panel missing | Sit in a car with an installed radio, open its radio window and expand the mod panel |
| Bridge offline | Open Pear, enable API Server, match host/port and authorize PZPearCarRadio |
| Console title says "Select" and updates stop | Press Esc in that window; Windows text selection can suspend the process. Current versions disable QuickEdit at startup |
| API responds but music is silent | Play a song manually in Pear; check battery, power and pause state, then press Pause and Resume |
| Bridge works but game cannot see it | Use the same Zomboid directory for both; inspect `Zomboid/Lua/PearCarRadio.status.txt` |
| Lua errors | Search `%USERPROFILE%\Zomboid\console.txt` for `PearCarRadio` |

For a custom directory, install with `-ZomboidDir 'D:\MyZomboid'` and launch with `Start-Bridge.cmd --zomboid-dir "D:\MyZomboid"`. For another port, pass `--port 26539` and configure the same port in Pear.

## Development

Code, comments, UI strings, logs, documentation and commit messages use English.

Run `python -m unittest discover -s tests -v`. To enable the optional Lua 5.1 harness, install `python -m pip install --target .tools lupa` and rerun. This dependency is for development only.

Tests cover file snapshots, HTTP requests, simulated Pear playback and Lua behavior against a game API harness. They do not replace actual game/Pear testing. The bridge uses Python's standard library. The mod extends `ISRadioWindow` and exchanges files to keep network requests off the game thread.

The protocol uses `Zomboid/Lua/PearCarRadio.control.txt` and `PearCarRadio.status.txt`. Snapshots include a session, counter and final write marker. Incomplete/stale commands are rejected. The bridge requires fresh state before taking control and does not repeat a button after losing its response. Very fast presses can collapse into one action. An OS lock prevents duplicate bridges for the same Zomboid directory.

Next steps: in-game links, refined Escape-menu behavior, and multiplayer song/time coordination. World noise must be server-controlled in multiplayer.

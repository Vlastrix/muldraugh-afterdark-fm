# Muldraugh Afterdark FM [B42.21]

**Works with Project Zomboid Build 42.21 (singleplayer).** Mod version **0.5.1**, experimental. Playback was tested by the author in v0.5.0 with Pear 3.12.0; v0.5.1 renames the app to Afterdark FM Connector. Other game builds and multiplayer have not been verified.

Play the **song or playlist already open in Pear Desktop** through **94.46 MHz Afterdark FM** on your car radio. Audio plays in Pear; the mod does not download or retransmit music.

## Player setup

**Afterdark FM Connector** is the Windows app that connects the mod to Pear. **Players do not need to install Python or use a command prompt.** Pear Desktop and Connector must stay open while playing.

You need three parts: the **[Workshop mod](https://steamcommunity.com/sharedfiles/filedetails/?id=3821956623)**, **[Pear Desktop](https://github.com/pear-devs/pear-desktop)**, and our **[Windows Connector ZIP](https://github.com/Vlastrix/muldraugh-afterdark-fm/releases/download/v0.5.1/AfterdarkFMConnector-Windows-0.5.1.zip)**. See the [v0.5.1 test release](https://github.com/Vlastrix/muldraugh-afterdark-fm/releases/tag/v0.5.1) for release notes and checksums. Extract the entire Windows ZIP; GitHub's source-code archives are for developers.

1. Open Pear Desktop / YouTube Music, select a song or playlist and verify playback.
2. In Pear Desktop, open **Plugins** and enable the included **API Server** plugin. In that plugin's settings, use hostname `127.0.0.1`, port `26538`, and **Auth at first** authentication. No router port forwarding is required. API documentation is available at <http://127.0.0.1:26538/swagger> while enabled.

   ![Pear Desktop Plugins menu with API Server [Beta] enabled and its Hostname, Port and Authorization strategy settings](assets/pear-api-server.png)

3. Subscribe to the game mod in Workshop. Enable only one copy of the mod; remove local development copies before testing a Workshop download.
4. Extract the Windows Connector ZIP and double-click **AfterdarkFMConnector.exe**. It connects automatically. Authorize **PZPearCarRadio** in Pear when prompted and keep the app open.
5. Start Zomboid and enable **Muldraugh Afterdark FM**. For an existing save, use **Load → More → Choose mods**. A test save is recommended.
6. Enter a car with an installed radio and a charged battery. Open its radio from the vehicle menu (`V`) and switch it on. Select **94.46 MHz Afterdark FM** under **Channel**, then press **Tune in**. The panel also has a **Tune to Afterdark FM** shortcut.
7. Use the normal radio volume control and **Previous / Pause / Next**. Unpause the game to play music.

Click **Disconnect** or close the app when finished. Forcefully terminating its process can prevent the final pause command. Close any older bridge before opening the connector; only one can control the same game folder.

The Workshop package contains the game mod; the connector is a separate Windows download because the game's Workshop validator rejects executables. See the [quick start](docs/QUICK_START.txt) and [publishing guide](docs/PUBLISHING.md).

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
- The connector currently supports Windows. Workshop alone will not launch it.
- Playback, content availability and account access depend on Pear. The mod never receives your Google password.

## Updating

Update the Workshop mod and download the matching connector release, then restart both. During local development, install with **Install-Mod.ps1** and use the newly built EXE.

During development, the project supports the current version without save migrations or backward-compatibility layers. Breaking changes may require a new world with the mod enabled; the update instructions will say when to create one. Old presets and saved data are not upgraded automatically.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Mod missing | Restart Zomboid, use the supported Build 42.21 and enable the mod for the save too |
| Panel missing | Sit in a car with an installed radio, open its radio window and expand the mod panel |
| Bridge offline | Open Pear, enable API Server, match host/port and authorize PZPearCarRadio |
| Connector cannot connect because another bridge is running | Close the old connector or bridge console, then click Connect |
| API responds but music is silent | Play a song manually in Pear; check battery, power and pause state, then press Pause and Resume |
| Bridge works but game cannot see it | Use the same Zomboid directory for both; inspect `Zomboid/Lua/PearCarRadio.status.txt` |
| Lua errors | Search `%USERPROFILE%\Zomboid\console.txt` for `PearCarRadio` |

For a custom user directory or API port, use the connector's **Settings** before connecting. Connection details appear in its window; the rotating log is stored at `Zomboid/Lua/AfterdarkBridge.log`.

## Development

See the [multiplayer plan](docs/MULTIPLAYER_PLAN.md) for shared-radio behavior, audio streaming between Connectors, milestones and open decisions. The `feature/multiplayer-audio` branch includes an experimental [audio lab](docs/AUDIO_LAB.md): only the sender needs Pear; listeners receive audio in Connector. Game multiplayer is not implemented, and the published v0.5.1 release remains singleplayer only.

The [game network research](docs/GAME_NETWORK_RESEARCH.md) identifies a candidate audio route over Zomboid's existing mod-command connection, aiming to avoid a separate VPN or audio port. Live multiplayer performance has not been verified.

Code, comments, UI strings, logs, documentation and commit messages use English.

The experimental audio build requires Python 3.12 with `requirements-build.txt`; the singleplayer CLI still uses Python 3.9 or later. Install the local mod with `powershell -ExecutionPolicy Bypass -File .\Install-Mod.ps1`. The developer CLI remains available with `python bridge/pear_bridge.py`; `Start-Bridge.cmd` opens the published singleplayer app when available. The experimental app builds separately under `dist/0.6.0-dev`.

Build the Windows download and separate Workshop package with `powershell -ExecutionPolicy Bypass -File .\Build-Release.ps1`. This creates an isolated build environment and bundles Python and Tcl/Tk into the EXE using PyInstaller. A GitHub Actions workflow also builds on manual dispatch or version tags. See [publishing](docs/PUBLISHING.md) for the upload checklist. Built artifacts and local credentials are excluded from Git.

Run `python -m unittest discover -s tests -v`. To enable the optional Lua 5.1 harness, install `python -m pip install --target .tools lupa` and rerun. This dependency is for development only.

Tests cover file snapshots, HTTP requests, simulated Pear playback and Lua behavior against a game API harness. They do not replace actual game/Pear testing. The bridge uses Python's standard library. The mod extends `ISRadioWindow` and exchanges files to keep network requests off the game thread.

The protocol uses `Zomboid/Lua/PearCarRadio.control.txt` and `PearCarRadio.status.txt`. Snapshots include a session, counter and final write marker. Incomplete/stale commands are rejected. The bridge requires fresh state before taking control and does not repeat a button after losing its response. Very fast presses can collapse into one action. An OS lock prevents duplicate bridges for the same Zomboid directory.

Next steps: in-game links, refined Escape-menu behavior, and multiplayer song/time coordination. World noise must be server-controlled in multiplayer.

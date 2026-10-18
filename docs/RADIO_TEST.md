# Multiplayer radio integration test

Experimental version: **0.7.5-dev**, targeting **Project Zomboid Build 42.21**. The 0.6.2-dev game-network test tone and Pear music were confirmed by the user between two players on October 18, 2026. The user subsequently confirmed radio audio and shared controls in 0.7.0-dev with both Connectors in Radio mode. Shared source volume and channel UI synchronization in 0.7.5-dev have automated coverage and still need live verification. The public Workshop release remains singleplayer only.

## Install on both computers

1. Close Zomboid and every running Connector/lab window.
2. Extract `MuldraughAfterdarkFM-Game-Test-0.7.5-dev.zip`. Put its `AfterdarkGameLab` folder in `%USERPROFILE%\Zomboid\mods`, replacing the previous test copy. The host can use `Install-GameLab.ps1` after building.
3. Enable **Muldraugh Afterdark FM Game Lab [B42.21]** in the server's Mods list. Install the same folder on a separate server machine if applicable. This local test has no Workshop ID. Keep the public singleplayer mod disabled on this test server.
4. Extract the entire `AfterdarkFMConnector-Windows-0.7.5-dev.zip` on both computers. Start its EXE. The app starts disconnected. Open **Multiplayer radios (Steam)** and press **Start**.
5. Listeners leave **Allow Use my Pear** unchecked. They do not need Pear, an API server, a music account, a separate VPN or an extra audio port.
6. Anyone who wants to supply music opens Pear, enables its **API Server plugin** on `127.0.0.1:26538` with **Auth at first**, selects a song/playlist, checks **Allow Use my Pear**, selects the Pear process and presses Start. Authorize `PZPearCarRadio` in Pear if prompted. The process list can be refreshed before Start.

No persistent radio session/save data is introduced in this iteration. Restart the game and server to load updated Lua; a new world is not required by this change.

## Car test

1. Both players enter a powered car with an installed radio. Turn the radio on.
2. Open its radio panel and expand **Muldraugh Afterdark FM**. Press **Tune to Afterdark FM** (normally **94.6 MHz**), then **Use my Pear** on the supplying player's panel. Wait for the owner/song to appear.
3. The passenger should hear the owner's Pear audio through their Connector. Test **Previous**, **Pause/Resume** and **Next** from the passenger's panel. These commands control the owner's queue.
4. The passenger exits and walks away: music should fade and stop beyond the audible radius. Returning should resume reception of current audio. The owner's session continues after leaving the car while its radio remains powered, tuned and loaded.
5. If the passenger also enabled Pear sharing, re-enter and press **Use my Pear** to take over. The previous owner's controlled Pear should pause; subsequent buttons must affect the new owner. **Stop sharing** releases the current owner's session.
6. Change the radio volume and verify both players hear the change, including zero. Confirm the native channel dropdown and Tune button agree on 94.6 MHz after tuning. Turn the radio off, switch to another station or remove its power. Reception and the owner's controlled playback should stop. Retune and explicitly take ownership to restart.
7. Disconnect the owner's Connector or leave the server. The session should stop after the heartbeat timeout; another player must explicitly take ownership.

Only occupants may control a vehicle radio. Nearby listeners cannot take over or issue playback commands.

## Placed radio test

Use a radio placed in the world, including a dropped radio represented by an `IsoWaveSignal`. Stand within two tiles on the same floor, provide power/battery, open its radio window and follow the same tuning/ownership steps. A nearby second player should hear it, control it within two tiles and hear distance attenuation when walking away. Picking up/removing the radio should end its session. TVs and radios held in inventory are excluded from this iteration.

## Current limits and observations to record

- **Owner monitoring remains direct Pear playback.** The owner does not receive a delayed duplicate stream. Radio volume is shared: the owner's Connector applies it to Pear before capture, so both owner and listeners hear it. Listener output applies distance attenuation without applying radio volume a second time. The owner's own distance fade is still pending. The original Pear volume is restored when sharing ends. Change the game's radio volume rather than Pear's slider while sharing.
- One session per owner, up to four source sessions and nine participating Connectors per server. At most eight remote listeners receive a source. Each listener follows one source: their own source takes priority while transmitting; otherwise an occupied car takes priority, then the strongest nearby radio. Multiple simultaneous streams/mixing are not implemented.
- Physical power and station state are checked on the server. Sources that unload or change object identity are released. Shared controls require the current session, server-validated position and an increasing request ID. Buttons have a short cooldown and an eight-command bounded queue.
- Server-added zombie noise requires recent owner playback confirmation and recent accepted audio. It follows source volume, with roughly 35 tiles at full volume. Native radio/vehicle noise can also occur; verify behavior in the game, including static text suppression.
- Capture, HTTP, encoding and output run outside Lua. Audio still uses reliable game commands, so measure delay, stutters and gameplay impact with realistic server latency. Dedicated servers remain unverified.

Record owner names, which buttons were pressed, whether both players can take over, listener fade, station/power behavior, radio removal and any game/Connector error. Test the existing singleplayer release separately before publishing multiplayer support.

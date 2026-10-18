# Game network lab: test without a separate VPN

This is an experimental test of audio over Project Zomboid's existing mod-command connection, targeting Build 42.21. The user confirmed the 0.6.2-dev tone and Pear music between two players on October 18, 2026. Radio integration in 0.7.3-dev still needs live testing; see [Multiplayer radio test](RADIO_TEST.md). The public v0.5.1 release does not include it.

No audio IP address, invitation, port forwarding or VPN is configured in Connector for this mode. Both players must already be able to join the same Zomboid server through the game's normal network setup. Listeners do not need Pear. The test server forwards encoded batches in Lua and needs no Pear, Connector or external audio service.

## Install the local test mod

The build produces two downloads for this experiment:

- `AfterdarkFMConnector-Windows-0.7.3-dev.zip`: extract the entire ZIP on both computers. Run `AfterdarkFMConnector.exe`.
- `MuldraughAfterdarkFM-Game-Test-0.7.3-dev.zip`: extract its `AfterdarkGameLab` folder into each client's user `Zomboid/mods` directory. Install that folder in the test server's user `Zomboid/mods` directory too if the server uses another machine/user folder.

The test mod has its own **local Mod ID `AfterdarkGameLab`**, named **Muldraugh Afterdark FM Game Lab [B42.21]**. This is not a second Workshop item. It avoids replacing the subscribed public `PearCarRadio` copy. Do not publish the test package as verified multiplayer support.

Close the game before installing or updating. On the host, the developer helper `powershell -ExecutionPolicy Bypass -File .\Install-GameLab.ps1` installs the built test mod. Alternatively copy `dist/0.7.3-dev/Test-Mod/AfterdarkGameLab` into `Zomboid/mods` manually.

Enable the Game Lab mod in the hosted test server's mod settings. On a dedicated server, add `AfterdarkGameLab` to its `Mods` setting and install the same local files; no new `WorkshopItems` entry is needed. Clients must have matching files. Restart the server and clients after changes. Use a test world with the lab enabled. Restart to load updated files. Do not enable a full local experimental `PearCarRadio` copy alongside the standalone lab: both contain these transport scripts. The subscribed public v0.5.1 mod can remain installed.

## First test: solo server round trip, no Pear required

You can begin without a friend. Install and enable the local test mod, host a fresh multiplayer test world, open the experimental Connector, disconnect the normal bridge and launch the EXE with `--game-lab`. Select **Send test tone** and press **Start**.

The **Prepared**, **Game sent** and **Confirmed echo** counters should increase. Prepared counts locally encoded batches; Game sent counts submissions by Lua to the game transport. The server returns each synthetic audio batch, and the client compares it with the original local snapshot. This checks the existing game connection in both directions without another player. The sender does not play the echoed tone locally, so this solo check is intentionally silent. A successful echo does not establish playback on another computer or acceptable Internet performance.

Version 0.6.2-dev fixes a reproduced control-file race: reading a snapshot during its rewrite previously made Lua leave the room and reset its counters. Lua now retains the last complete heartbeat for at most two seconds from its original timestamp. An explicit Stop still leaves immediately. Counters remain cumulative for the same Connector run, including room reconnections; **Room changes** counts transitions to a different nonempty room after the first assignment. A new Connector run resets the counters. There is no 1,200-batch limit.

For the next live check, restart the Connector, game and test server after updating both packages. Run the solo tone for at least four minutes. Record Prepared, Game sent, Confirmed echo, Skipped local/game and Room changes. During uninterrupted operation, the first three should advance together with small timing differences and Room changes should remain zero. The automated regression covers 1,305 batches with partial control reads; the user subsequently confirmed stable solo counters and audio between two computers. Broader latency and performance measurements remain pending.

## Second test: two computers, no Pear required

1. Host a Build 42.21 multiplayer test world with the Game Lab mod enabled. Your friend joins normally through Zomboid/Steam.
2. Both players open the experimental Connector. Disconnect its normal singleplayer bridge, then launch the EXE with `--game-lab`. Check that the **Zomboid user folder** matches the running game on each computer.
3. On the receiving computer, leave **Listen** selected and press **Start**.
4. On the sending computer, select **Send test tone** and press **Start**. The source is a quiet generated 440 Hz tone; it does not capture desktop sound.
5. The sender should show **Sending through the game connection**. The listener should show **Receiving through the game connection**, hear the tone and see the received-batch counter increase. Adjust the listener volume slider locally.
6. Compare the game ping/FPS with the test stopped and running. Watch the displayed RTT, skipped batches and server-rejected counts. RTT measures the game command round trip, not complete audio latency.
7. Press **Stop** on the sender. The listener should stop receiving; the source session is cleared. With no explicit Stop, stale source membership expires after about three seconds. A second player can then start sending.

Only lab participants hear the test stream. It is not tied to a vehicle, radio power or distance. One active source and up to eight listeners are allowed. A second attempted source sees **Another player is sharing**; it cannot override the current source in this milestone.

## Third test: share Pear

After the tone works, stop the source, open Pear, select a song and verify normal playback. Keep the old singleplayer bridge closed so it cannot change Pear volume. Select **Share my Pear**, choose the detected process and press **Start**.

This capture mode does not call Pear's API, so API Server authorization is not a prerequisite for this audio-only test. It will be needed for future remote Pear controls. Capture remains process-specific and rejects desktop-wide fallback. Capture requires Windows build 20348 or later and the native 48 kHz stereo format supported by the earlier audio lab. The receiver still does not need Pear.

Do not mute Pear to silence the sender's speakers: capture may follow its volume. The sender hears Pear directly, without a second delayed local copy. Source monitoring and capture/local gain separation need more work before vehicle integration.

## What to report

- Client/server game build and confirmation that both loaded the local Game Lab mod.
- Whether tone and Pear playback arrive, and whether unrelated app audio stays excluded.
- Whether Start, Stop, source disconnect and listener reconnect behave correctly.
- RTT and skipped/rejected counts; game ping, FPS and server tick behavior before/after sharing.
- Audible gaps, delay or old audio continuing after a pause/stop.

If the sender waits for **server transport**, check the server's enabled mods and local install. If there is **no game signal**, check the client mod and selected Zomboid folder. Lua errors appear in the game's `console.txt` or server logs. The normal public Workshop mod alone does not provide the lab.

## Implementation and automated checks

The source encodes stereo audio at 48 kHz using 64 kbit/s constant-bitrate Opus, in 20 ms frames. Two frames form a 40 ms Base64 batch: typically 440 ASCII characters, about 25 messages/s. The server validates the connection-derived source, local client token, current room, increasing sequence, payload size and a 30-batch/s ceiling before forwarding only to enrolled listeners. No full-desktop capture, server-side audio decoding or global change to game packet settings is used.

The local bridge uses fixed `.txt` snapshots and a 16-slot ring. Commit markers reject partial writes. Each poll handles a bounded recent batch window, checks local age and drops backlog rather than accumulate unlimited audio. Opus decoders reset after sequence gaps or room changes. Main game loops still perform bounded file I/O and command forwarding; real performance must be measured.

Tests execute the actual transport Lua scripts in separate Lua 5.1 realms with queued network calls and real temporary bridge files. A real Opus encode/decode batch passes from Connector through the client/server Lua harness and back to Connector. This does not exercise the real Java serializer, Steam/RakNet, game UI, server timing or two-computer audio output. Treat the live test as the next required validation.

Vehicle ownership, **Use my Pear**, remote Previous/Pause/Next, distance attenuation and server zombie noise remain future milestones. The existing singleplayer implementation and published compatibility claims are unchanged.

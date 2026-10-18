# Using Zomboid's existing connection for audio

Research date: 2026-10-18. Target inspected: the installed Project Zomboid Build 42.21. This is a feasibility investigation, not verified game multiplayer support.

## Conclusion

**There is a credible Lua-accessible route to prototype audio over the existing game connection.** Mod commands carry serializable tables from a client to the server, and the server can send tables to specific clients. The shipped `Util/LuaNet.lua` already implements client-to-client forwarding on top of those commands.

Proposed path:

`Pear -> sender Connector -> local bridge -> sender Lua -> existing game connection -> server Lua -> existing game connection -> listener Lua -> local bridge -> listener Connector output`

If the streaming experiment succeeds, listeners who can already join the game server would not need a VPN, another public audio port or a separate Internet audio connection. This reuses whatever connection route the game established, including a Steam route when selected. It does not require Connector to initialize Steamworks or gain its own Steam relay access. Normal game-server connectivity remains a prerequisite.

Static inspection and a mocked Lua forwarding check establish a candidate transport, not acceptable latency, reliable throughput or performance in a live session. Do not promise this as a released feature yet.

## Local primary evidence

Inspected the installed `projectzomboid.jar` and shipped Lua files, without modifying them. `Core` initializes the version as 42.21. The inspected JAR's SHA-256 is `e1a69eb743ede60b213a0fe7f8b83d4fcab773036d256cc4543a336f3b058a33`. Decompiler output stays under ignored `.tools/network-research` and is not distributed with this project.

| Location | Finding | Consequence |
| --- | --- | --- |
| `LuaManager.GlobalObject.sendClientCommand` | A global Lua function forwards a module, command and argument table through `GameClient` in an active multiplayer session. | A Lua mod can submit an encoded audio batch through the game. |
| `GameServer.receiveClientCommand` | Decodes the arguments, resolves the player from the actual connection, and raises `OnClientCommand`. | The server can validate the real sender before accepting audio. |
| `LuaManager.GlobalObject.sendServerCommand` / `GameServer.sendServerCommand` | Can target a specific player rather than broadcast to every connection. | Relay only to authorized listeners who should hear this source. |
| `GameClient.receiveClientCommand` | Decodes the server's arguments and raises `OnServerCommand`. | Listener Lua can deliver a batch to its local Connector. |
| `media/lua/shared/Util/LuaNet.lua` | Its `sendPlayer` and `listen` paths implement server forwarding between clients. It wraps the same mod-command transport. | This is an existing use of the intended route, not a new native networking API. |
| `UdpEngine` and `RakNetPeerInterface` | The engine initializes the peer in Steam mode when appropriate and passes the relay choice through its connection calls. | Mod commands use the established game network path; inspecting these Java calls does not establish which native Steam relay implementation every session uses. |

## Payload encoding and size

`TableNetworkUtils` handles strings, doubles, booleans and nested tables, along with some game object types. It does not expose an arbitrary byte-array payload through the normal Lua command table. String values are written using UTF-8, so raw compressed audio bytes must not be treated as arbitrary text. Base64 is the straightforward candidate encoding.

In the inspected build, the string writer stores the encoded byte length in a signed 16-bit field and `ByteBufferReader.getUTF` reads a signed short. Keep every encoded string well below 32,768 UTF-8 bytes. This is a serialization boundary, not a sensible streaming packet target. Start with small batches around or below 1 KiB of encoded audio, and validate total message size separately. The underlying one-million-byte connection buffer is not a recommended or safe streaming payload budget.

## Delivery and traffic limits

The inspected `ClientCommand` packet uses high priority and reliable delivery, with ordering channel zero. Reliability value 2 means **reliable, unordered**, not reliable ordered. The Lua command functions do not offer a per-message switch to an unreliable or separate audio channel. Do not change the global packet type's reliability: it is shared with other mod and game commands.

Reliable delivery can retransmit obsolete audio and consume bandwidth during poor network conditions. Session IDs, sequence numbers, bounded buffers and a strategy for discarding late batches are necessary. This transport is not a dedicated real-time audio channel.

`PacketsCache.isLimitExceeded` accounts for packet types per connection. `PacketType.send` can cancel outgoing client packets when the limit is exceeded. In the inspected `ServerOptions`, `MaxPacketsPerSecond` defaults to 300, with a configured range of 100 to 1000. Other mod commands share the `ClientCommand` packet type, so this is not an audio-only allowance. The inspected server-side receive path logs a limit finding; do not generalize that into an automatic disconnect or assume all configurations permit unlimited traffic.

`GameServer.receiveClientCommand` also writes command log entries according to `ClientCommandFilter`. That filter controls this logging in the inspected method; it is not an authorization rule for our audio. The prototype must measure log growth and avoid treating the filter as a security mechanism. Do not disable anti-cheat or increase server-wide packet limits just to make streaming pass.

Handlers run through game networking/main-loop processing and Lua events. Encoding, decoding and audio work must remain in Connector; Lua should perform only bounded checks, forwarding and local bridge I/O. The existing half-second singleplayer state-file polling is not an audio bridge design and cannot be reused unchanged.

## Compression is required before a useful game test

The current audio lab sends zlib-compressed PCM over direct TLS. Lossless compression of PCM is not a suitable default for funneling music through the game command path. Prototype a music codec such as Opus and validate its actual output and bundled runtime before connecting this route to capture.

Illustrative payload budgets, not measured game results:

| Assumed codec bitrate | Encoded binary audio | Base64 audio only | With 40 ms batches |
| --- | --- | --- | --- |
| 64 kbit/s | 8,000 bytes/s | About 10.7 KB/s | About 25 command messages/s per source direction |
| 96 kbit/s | 12,000 bytes/s | About 16 KB/s | About 25 command messages/s per source direction |

These estimates exclude codec framing, command metadata, transport headers and retransmissions. Server egress grows with the number of listeners; four listeners require four outgoing deliveries for each batch. Multiple sources add more traffic. A low-volume, two-player experiment is appropriate before considering larger servers.

## Why not directly reuse voice chat or native sockets?

The game has a native voice path and low-level packet-send methods in Java. In the inspected Lua registration, `VoiceManager` offers mute operations and recording-device enumeration, without an exposed function to inject arbitrary captured PCM. The Lua exposure list does not directly register the low-level networking classes inspected here as a supported raw-stream interface.

That is not a proof that every possible native integration is impossible. It means there is no verified, ordinary Lua mod entry point from this investigation for a separate custom binary audio stream or Pear input injection into voice chat. Native hooks or game modifications would be a different distribution and maintenance approach. Prefer the exposed command route for the next experiment.

## Forwarding validation completed

Executed the installed, unmodified `Util/LuaNet.lua` in separate Lua 5.1 sender, server and listener runtimes. Mocked game events and command functions transported copied argument tables between the runtimes. Its built-in forwarding path delivered a 1,024-character Base64 payload with the session and sequence intact.

This check did **not** execute the Java byte-buffer serializer, real RakNet/Steam networking, a running game server or audio playback. No live throughput or latency has been measured. The prior native capture/TLS test belongs to the standalone audio lab and does not validate this proposed game route.

Do not copy LuaNet's automatic forwarding as our permission model. The audio server must validate the connection-derived sender, active vehicle owner, allowed listeners, session, batch size and rate before forwarding. Client-supplied source names and recipients are not sufficient authorization.

## Next experiment and acceptance criteria

1. Create an opt-in, separate multiplayer transport probe using our own `OnClientCommand` / `OnServerCommand` handlers. Start with small synthetic payloads, explicit listener selection and server-side size/rate limits, without audio or vehicle ownership UI.
2. In a real two-player Steam-connected game, verify round-trip delivery, session identity, actual payload lengths, message loss, late delivery and clean stop. No VPN, additional forwarded audio port or listener Pear installation should be necessary.
3. Add compressed synthetic audio through the local Connector bridge. Measure end-to-end delay, buffer age, command traffic, frame time, server tick time, game ping and log growth. Test background/paused menus and both host and dedicated-server modes before promising either.
4. Replace the synthetic source with process-only Pear capture. Verify unrelated-app exclusion, local gain separation, stopping, reconnecting and source replacement.
5. Proceed to the planned vehicle sessions only if audio and gameplay remain usable. If the reliable command route performs poorly, compare other transports and report the measured result rather than silently adding a VPN requirement.

The direct TLS audio lab remains useful for capture/output diagnostics. It is not the chosen user-facing requirement for final Internet multiplayer.

## External references

- [Project Zomboid 42.21 Stable announcement](https://projectzomboid.com/blog/news/2026/09/42-21-stable-released/) establishes the build context; the installed code is the evidence for the command and serialization details above.
- [Valve Steam Datagram Relay documentation](https://partner.steamgames.com/doc/features/multiplayer/steamdatagramrelay?l=english) describes Steam's relay service, without establishing that Connector can initialize or reuse it independently.
- [Valve GameNetworkingSockets](https://github.com/ValveSoftware/GameNetworkingSockets) distinguishes the open-source transport from Steam authentication, signaling and relay services.

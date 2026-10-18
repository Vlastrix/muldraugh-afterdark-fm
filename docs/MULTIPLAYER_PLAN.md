# Multiplayer plan

Status: the standalone audio-streaming prototype is implemented on `feature/multiplayer-audio`; game multiplayer is not implemented. The published mod supports Project Zomboid Build 42.21 in singleplayer only. Multiplayer compatibility must be verified separately before it is advertised.

## Current progress

The experimental Connector contains an [audio lab](AUDIO_LAB.md) with process-only Pear capture, a direct TLS sender, a listener that does not require Pear, invitation authentication, local output gain and bounded buffers. Automated local transport tests and a native synthetic two-process isolation test have passed. The packaged GUI and native imports have been smoke-tested. Actual Pear streaming between two computers, Internet connectivity, owner monitoring/gain behavior and game integration are still pending. The published singleplayer release remains separate from this prototype.

## Goal

Let the host and guests contribute music from their own Pear Desktop sessions, listen together through vehicle radios, and share playback controls. Keep development in the same repository and eventually update the existing Workshop item once both singleplayer and multiplayer have been tested.

The selected approach is to stream the music owner's actual Pear audio between Connectors. **Only players contributing music need Pear Desktop. Listeners need the mod and Afterdark FM Connector, without Pear or a YouTube account for reception.** This is the target game experience, not a feature of the current published release. The standalone audio lab can test reception before game integration.

Develop multiplayer on a separate Git branch. A second Workshop item is optional only if a distributed Steam beta becomes necessary; it is not required for the initial tests.

## Shared vehicle radio

Each vehicle has a shared radio session with one music owner: the player whose Pear supplies the current song and playback queue. The host has the same contribution and control rights as guests.

- An occupant with Pear installed and authorized presses **Use my Pear** to become the music owner for that vehicle. Listening and using shared controls do not require a local Pear installation.
- Other occupants can use **Previous**, **Pause**, **Resume** and **Next** to control the owner's Pear through the server and the owner's Connector.
- Another occupant can press **Use my Pear** to replace the current music owner with their own Pear selection. Show the active owner's name in the radio panel.
- The vehicle's radio volume is shared. Each listener's actual playback volume is adjusted locally using their distance from the vehicle.
- Leaving the vehicle does not end the owner's session while the owner remains connected, the vehicle remains available and its radio has power and is tuned to Afterdark FM.
- If the owner disconnects or their Connector becomes unavailable, stop the shared session. Another occupant can explicitly take ownership; do not silently select someone else's Pear.
- Switching away from Afterdark FM, losing radio power or removing the source stops controlled playback for that source.

Initial permission proposal: only occupants can take ownership or send playback commands. Nearby players can listen without gaining control. The server must validate requests rather than trust client-supplied ownership or position.

## How other players hear the music

Remote control alone does not transmit audio. Capture the owner's Pear audio, encode it, transmit it over the network and play it through each listener's Connector. Listeners do not open the same song in their own Pear instances, and do not need track-opening or seeking APIs to follow the owner.

Proposed audio path:

`Owner's Pear -> owner's Connector capture/encoder -> network transport -> listener's Connector decoder/output`

The music owner needs Pear Desktop, its API Server plugin enabled and authorized, the mod and Connector. Other listeners need only the mod and Connector. A listener who later wants to contribute music must first set up Pear locally. A dedicated game server does not need Pear or an audio device; a separate relay service may be required depending on the chosen transport.

Capture only Pear's process audio, including its relevant child processes, rather than the entire desktop or microphone. Verify process-specific loopback capture and supported Windows versions before choosing the capture implementation. Listeners receive whatever Pear actually outputs; capture must not accidentally include Discord, game sounds or notifications.

Initially, Connector will render the received audio outside the game's sound engine. The mod supplies radio state and listener distance so Connector can apply the correct local gain. Feeding a live network stream directly into Zomboid's sound engine remains unverified and is not required for this first approach.

Audio transport is separate from game control messages. Do not assume Zomboid exposes a suitable continuous-audio transport. Compare direct connections with a relay, including NAT traversal, upload bandwidth, hosting needs and session authentication. Select the transport after a small end-to-end prototype.

Use bounded buffering and handle packet loss, jitter, late joins and disconnects without replaying stale audio. A streamed listener will hear the source with some delay; do not promise sample-accurate synchronization. The owner keeps the authoritative Pear queue, and shared buttons still control that Pear through its API.

Resolve the owner's monitoring path during the prototype: hearing both Pear directly and a delayed received copy would cause an echo. Also verify that the existing Pear volume control does not attenuate captured audio for every listener when only the owner's local listening gain should change. Distance and car volume must be applied at the appropriate capture/output stages without feedback or double attenuation.

## Server authority and client responsibilities

The server owns vehicle session state, music ownership, permission checks and world noise. It orders accepted actions and rejects requests for invalid sessions. Ownership changes must invalidate commands and playback reports from the previous owner.

The owner's Connector handles local Pear authorization, capture and transmission. Listener Connectors handle reception and local audio output without requiring Pear. Account credentials and Pear API tokens stay on the owner's machine; do not send them through the game server or to listeners. Authenticate stream participants against the active session, and stop accepting audio from a previous owner after replacement. The existing singleplayer file bridge is a starting point, not evidence that audio streaming or multiplayer messaging already works.

World noise must be generated once by the server using vehicle power, radio volume and fresh playback confirmation. Listener distance attenuation must not reduce what zombies hear at the vehicle. Define whose playback confirmation is authoritative during the prototype; the proposed source is the active music owner.

## Initial scope and limits

- Vehicle radios first. Portable radios and radios placed in the world are future work.
- One vehicle session per music owner initially.
- A listener follows one source at a time initially to keep reception and source selection manageable. This is an initial scope choice, not a requirement imposed by Pear on listeners. Choosing between nearby sources remains a design decision; occupying a vehicle should take priority. Multiple simultaneous streams and mixing are future work.
- Windows audio capture first; verify the minimum Windows version and package runtime dependencies so players do not need development tools.
- Preserve the tested singleplayer experience while introducing multiplayer behavior.
- Do not claim support for a multiplayer game build until it has been tested, including a dedicated server when dedicated-server support is offered.

## Implementation sequence

1. Build an audio prototype outside the game: capture only Pear in the owner's Connector, encode/transmit it, and play it in a second Connector on another computer without Pear installed. Validate latency, capture isolation, gain behavior and the owner's monitoring path before expanding the implementation.
2. Choose the network transport and establish authenticated sessions. Implement a minimal two-player vehicle session where the server identifies the owner and eligible listeners, while audio flows between Connectors over the selected transport. Keep audio capture, networking and decoding off the game thread.
3. Route shared playback buttons through the server to the owner. Verify ordering, permissions and stale-command rejection.
4. Add **Use my Pear** ownership replacement and show the current owner. Check simultaneous requests and ensure the previous owner stops controlling the session.
5. Add shared volume, listener distance attenuation and server-controlled zombie noise. Test leaving the car, power loss and station switching.
6. Handle owner/Connector disconnects, unloaded or removed vehicles, source silence, packet loss, late joiners and reconnects. Bound retries and audio buffers; discard old buffered audio on ownership changes.
7. Test with host and guests, then with a dedicated server if included in the release. Verify singleplayer still works, document setup and limitations, and update the existing Workshop item only after verification.

## Decisions and checks still needed

- Exact Project Zomboid multiplayer build and exposed client/server APIs to target.
- Process-specific audio capture support, Pear subprocess selection and the minimum supported Windows version.
- Codec, sample rate, bitrate, audio output library and redistribution of required runtime components.
- Direct connections versus a relay, NAT traversal, relay hosting and bandwidth, session authentication and abuse limits.
- Separate capture gain from local listening gain, prevent the owner from hearing duplicate audio, and ensure capture is unaffected by the owner's distance from the car.
- Pear API behavior for shared playback controls and metadata; arbitrary track opening and seeking are not prerequisites for listeners.
- Source selection when several active vehicles are nearby, and behavior when a music owner is also near another owner's vehicle.
- Target latency, jitter-buffer limits and how to recover from stalls without playing obsolete audio.
- How to display owner authorization/capture failures, network failures and listener output problems.
- Whether to require confirmation or a short cooldown for ownership replacement.

The next validation is the two-Connector audio lab on separate computers, with Pear installed only on the transmitting computer. Integrate it with vehicle sessions and remote controls after that works. Radios in the world and broader polish follow later.

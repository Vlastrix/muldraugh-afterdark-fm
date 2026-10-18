# Multiplayer plan

Status: proposed design, not implemented. The published mod supports Project Zomboid Build 42.21 in singleplayer only. Multiplayer compatibility must be verified separately before it is advertised.

## Goal

Let the host and guests contribute music from their own Pear Desktop sessions, listen together through vehicle radios, and share playback controls. Keep development in the same repository and eventually update the existing Workshop item once both singleplayer and multiplayer have been tested.

Develop multiplayer on a separate Git branch. A second Workshop item is optional only if a distributed Steam beta becomes necessary; it is not required for the initial tests.

## Shared vehicle radio

Each vehicle has a shared radio session with one music owner: the player whose Pear supplies the current song and playback queue. The host has the same contribution and control rights as guests.

- An occupant presses **Use my Pear** to become the music owner for that vehicle.
- Other occupants can use **Previous**, **Pause**, **Resume** and **Next** to control the owner's Pear through the server and the owner's Connector.
- Another occupant can press **Use my Pear** to replace the current music owner with their own Pear selection. Show the active owner's name in the radio panel.
- The vehicle's radio volume is shared. Each listener's actual playback volume is adjusted locally using their distance from the vehicle.
- Leaving the vehicle does not end the owner's session while the owner remains connected, the vehicle remains available and its radio has power and is tuned to Afterdark FM.
- If the owner disconnects or their Connector becomes unavailable, stop the shared session. Another occupant can explicitly take ownership; do not silently select someone else's Pear.
- Switching away from Afterdark FM, losing radio power or removing the source stops controlled playback for that source.

Initial permission proposal: only occupants can take ownership or send playback commands. Nearby players can listen without gaining control. The server must validate requests rather than trust client-supplied ownership or position.

## How other players hear the music

Remote control alone does not transmit audio. The proposed design synchronizes playback in each listener's own Pear instance; it does not relay the owner's audio stream through the game server.

Every participating listener needs Pear Desktop and Afterdark FM Connector running locally, with the API Server plugin enabled and authorized. The server does not need a Pear account or audio application, including on a dedicated server.

The owner's Connector would report the current track identifier, playback position and play/pause state. The server would distribute this state to eligible listeners, whose Connectors would open the same track and align playback in their own Pear instances. The owner's queue remains authoritative; listeners follow track changes rather than maintain independent copies of that queue.

This depends on validating Pear's API capabilities. Opening an arbitrary track by identifier and seeking accurately have not yet been established as a working multiplayer integration. Prototype these operations before committing to the complete design. If they do not work reliably, revisit the listening approach before expanding the implementation.

Different account access, ads, unavailable tracks and loading delays may prevent a listener from reproducing the same audio or staying aligned. Handle these conditions visibly and keep them from interrupting the owner's playback. Do not promise sample-accurate synchronization.

## Server authority and client responsibilities

The server owns vehicle session state, music ownership, permission checks and world noise. It orders accepted actions and rejects requests for invalid sessions. Ownership changes must invalidate commands and playback reports from the previous owner.

Clients and their Connectors handle their own Pear authorization and local audio. Account credentials and Pear API tokens stay on each player's machine; do not send them through the game server. The existing singleplayer file bridge is a starting point, not evidence that multiplayer messaging or synchronization already works.

World noise must be generated once by the server using vehicle power, radio volume and fresh playback confirmation. Listener distance attenuation must not reduce what zombies hear at the vehicle. Define whose playback confirmation is authoritative during the prototype; the proposed source is the active music owner.

## Initial scope and limits

- Vehicle radios first. Portable radios and radios placed in the world are future work.
- One vehicle session per music owner initially.
- A listener follows one source at a time, because one Pear instance cannot independently mix several vehicle tracks. Choosing between nearby sources remains a design decision; occupying a vehicle should take priority.
- Preserve the tested singleplayer experience while introducing multiplayer behavior.
- Do not claim support for a multiplayer game build until it has been tested, including a dedicated server when dedicated-server support is offered.

## Implementation sequence

1. Validate Pear API track opening, playback position reporting and seeking with two local Connectors or two players. Establish how Connector receives remote playback instructions without blocking the game thread.
2. Implement a minimal two-player vehicle session: one owner contributes a track and the second player hears the same track through their own Pear.
3. Route shared playback buttons through the server to the owner. Verify ordering, permissions and stale-command rejection.
4. Add **Use my Pear** ownership replacement and show the current owner. Check simultaneous requests and ensure the previous owner stops controlling the session.
5. Add shared volume, listener distance attenuation and server-controlled zombie noise. Test leaving the car, power loss and station switching.
6. Handle owner/Connector disconnects, unloaded or removed vehicles, unavailable tracks, late joiners and reconnects. Bound retries and synchronization corrections.
7. Test with host and guests, then with a dedicated server if included in the release. Verify singleplayer still works, document setup and limitations, and update the existing Workshop item only after verification.

## Decisions and checks still needed

- Exact Project Zomboid multiplayer build and exposed client/server APIs to target.
- Pear API support and behavior for track selection, seeking and current playback position.
- Whether starting local radio listening should require explicit consent before replacing music already playing in a listener's Pear.
- Source selection when several active vehicles are nearby, and behavior when a music owner is also near another owner's vehicle.
- How frequently to send state and correct drift without repeated seeking or audible interruptions.
- How to display authorization problems, unsupported tracks and listeners that cannot synchronize.
- Whether to require confirmation or a short cooldown for ownership replacement.

The next milestone is the two-player playback and remote-control prototype. Radios in the world and broader polish follow after this foundation works.

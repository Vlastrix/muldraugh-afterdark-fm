# Connector audio lab

Experimental branch: `feature/multiplayer-audio`. This is the first multiplayer-plan milestone, not multiplayer support in Zomboid. The published v0.5.1 release does not contain this lab.

## What works in the prototype

- A sender can select a detected Pear process and capture its process tree on supported Windows systems. System-wide capture fallback is explicitly rejected.
- A listener receives and plays audio in Connector without Pear or a Pear API authorization.
- Audio travels over a direct TLS connection. The invitation contains the server certificate fingerprint and a random session key. It changes when sharing restarts. Do not post an invitation publicly.
- Listener volume changes only local output. Capture/network/output buffers are bounded and old queued audio is discarded.
- Up to eight connected or authenticating listeners are allowed per sender. Slow network writes do not block the capture thread.

The prototype uses 48 kHz stereo int16 PCM in 20 ms frames, independently compressed with zlib. This is a simple lossless test format, not the final music codec. Budget roughly 1.5 Mbit/s per listener before compression and overhead; actual use depends on the audio. Codec selection and bandwidth optimization remain open.

## Test with two computers

Use the same trusted LAN or an existing private VPN. There is no relay, NAT traversal or automatic discovery. Do not expect an invitation containing a private LAN address to work over the public Internet.

1. Close the old Connector on the sender so its singleplayer bridge does not change Pear volume. Keep Pear playing a song at an audible volume. The audio lab does not call Pear's API or change its volume.
2. Open the experimental `AfterdarkFMConnector.exe`, disconnect the normal singleplayer bridge, then click **Audio lab**. From source, use `python bridge/desktop_app.py --audio-lab`.
3. On the sender, select **Share my Pear**, press **Refresh**, and choose Pear's process. Check the LAN/VPN address and use the default port `26539`. Press **Start**. The capture peak indicates whether samples are arriving.
4. Copy the invitation privately to the listener. If Windows Firewall prompts on the sender, allow the app on the private network used for this test. The app does not configure firewall/router rules automatically.
5. On the second computer, open the same lab, select **Listen (no Pear required)**, paste the invitation and press **Start**. Start with low listener volume and adjust the slider.
6. Press **Stop** or close the lab to disconnect. Stopping the sender does not pause Pear; it stops capture and network sharing. Restarting sharing creates a new invitation.

Capture requires Windows build 20348 or later; Windows 11 is recommended for the first test. The capture module currently requires native 48 kHz stereo float32 capture and fails visibly if that format or process isolation is unavailable. There is no microphone or full-desktop capture option.

The sender hears Pear directly; the sender lab does not also play a delayed copy. Do not use a listening lab on that same computer as evidence of process isolation or a realistic latency test. Other running audio must be excluded by process capture, not merely quiet during the test.

## Not integrated yet

This lab is independent of the game. It has no vehicle ownership, **Use my Pear** button, remote Pear controls, automatic distance volume, server-controlled zombie noise or multiple-source selection. Those belong to subsequent milestones. Do not update the public Workshop description to claim multiplayer support.

TCP/TLS can stall under packet loss. The current receiver disconnects on a read timeout rather than attempt to resume parsing a partial frame. There is no automatic reconnection. Buffers are bounded but end-to-end latency and behavior on poor networks still require two-computer testing.

Singleplayer currently controls Pear's numeric volume. Before vehicle integration, separate capture gain from each listener's gain so an owner's distance never reduces audio for everyone. This is intentionally unresolved in the standalone lab.

## Developer build and verification

Build with Python 3.12 and `requirements-build.txt`; it includes `requirements-streaming.txt`. Players use the bundled EXE and do not install Python or these dependencies. If a previous `.tools/build-env` uses Python 3.9, create a separate Python 3.12 environment rather than reuse it.

Run `python -m unittest discover -s tests -v` with the streaming dependencies installed. TLS tests use local sockets and synthetic PCM, not Pear or the game. Capture-isolation guard tests simulate a library that falls back to desktop audio. The build smoke-tests both GUI windows and imports the bundled native capture/output modules without starting capture.

Report actual Pear capture, other-app audio isolation, listener output, stop/restart and two-computer latency separately from automated results.

Development verification completed: a local native test rendered two low-level synthetic tones in separate processes, captured just one process, sent 75 audio frames through real TLS sockets and confirmed that the unrelated process tone was excluded. This was a one-computer transport/isolation check, not a Pear or two-computer latency test.

Capture backend: [ProcTap](https://github.com/m96-chan/ProcTap), using Windows process loopback. Windows platform reference: [Microsoft application loopback sample](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/). Output backend: [python-sounddevice](https://python-sounddevice.readthedocs.io/).

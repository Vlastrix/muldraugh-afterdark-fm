# Publishing the Windows Connector and Steam Workshop mod

The `feature/multiplayer-audio` branch builds a local **0.7.2-dev** audio prototype under `dist/0.7.2-dev`. Do not publish it as game multiplayer support. The v0.5.1 instructions below describe the existing public singleplayer release; see [Multiplayer radio test](RADIO_TEST.md) for experimental testing.

The packages are separate. The installed game's Workshop validator rejects executable file types, including `.exe` and `.dll`. Never put the connector inside `Contents`. Players download the connector from GitHub and subscribe to the game mod in Workshop.

The existing Workshop item is **3821956623**. Update this item rather than creating another one. Its title is **Muldraugh Afterdark FM [B42.21]** and its description explicitly states support for Build 42.21 in singleplayer.

## Build and verify

1. On Windows, run `powershell -ExecutionPolicy Bypass -File .\Build-Release.ps1`.
2. Output is under `dist/0.5.1/`: a player ZIP, an EXE for local testing, a Workshop ZIP, an unpacked Workshop folder and SHA-256 checksums.
   If the previous EXE is running, use `.tools/build-env/Scripts/python.exe tools/build_release.py --output-dir dist/publish-0.5.1` to build without interrupting it.
3. The build launches the packaged GUI in hidden smoke-test mode. It validates the Workshop preview size, mod metadata and absence of executable files in `Contents`.
4. Test the EXE with Pear and the mod in a fresh singleplayer world. Check connection/authorization, switching stations, leaving the car, distance volume and clean app shutdown. Automated tests do not replace this check.

## GitHub download

Create a GitHub Release for version `v0.5.1` and attach the Windows Connector ZIP and `SHA256SUMS.txt`. The Workshop ZIP is for the author to stage an upload, not for players to execute. Verify the player download before making the Workshop page public. Do not commit built executables or local game files to Git.

Use `docs/releases/v0.5.1.md` as the release notes, mark the release as a **prerelease**, and attach `QUICK_START.txt` separately as well. The public checksums should cover the files attached to the release. Download the uploaded ZIP and compare its SHA-256 hash with the local package before announcing it.

The connector ZIP includes the executable, player instructions and runtime notices. Players extract it and double-click the EXE; no separate Python installation or console is required. Keep `docs/QUICK_START.txt` with the download.

## Workshop upload

1. Copy `dist/0.5.1/Workshop/MuldraughAfterdarkFM` into your user `Zomboid/Workshop` directory. Its `preview.png`, `workshop.txt` and `Contents` must remain together.
2. In Project Zomboid, use **Workshop → Create and update items**, then select **MuldraughAfterdarkFM**. Review the title, description, preview, tags and game version.
3. On the first upload, start with **Private** visibility. For the existing published item, preserve `id=3821956623` and its current visibility in the generated `workshop.txt`. Never overwrite the ID with the template, which deliberately has no ID.
4. Subscribe and test the actual uploaded package. Remove/disable your local development copy first so it cannot hide mistakes in the Workshop version.
5. Once the connector download and subscribed mod work together, replace the description's release-pending wording with the actual download instructions, review visibility and publish publicly.

The prepared description clearly says the Windows Connector and Pear are required, that the mod is singleplayer only, and that music selection takes place in Pear. Never advertise multiplayer or in-game URL loading before those features work.

No Workshop item is uploaded by the build scripts. Uploading and changing visibility happen through your Steam account in the game.

Zomboid can load local mods from the Workshop upload folder too. After publishing, move that folder outside your user Zomboid directory before testing a subscribed copy. Preserve the generated metadata and item ID for the next update; do not install a second local copy with `Install-Mod.ps1` during this check.

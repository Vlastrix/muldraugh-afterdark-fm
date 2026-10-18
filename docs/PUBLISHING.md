# Publishing the Windows Connector and Steam Workshop mod

Published on October 18, 2026: [GitHub prerelease v0.8.0-beta.1](https://github.com/Vlastrix/muldraugh-afterdark-fm/releases/tag/v0.8.0-beta.1) and [existing Workshop item 3821956623](https://steamcommunity.com/sharedfiles/filedetails/?id=3821956623). The three public GitHub downloads were checked against local SHA-256 hashes. Steam returned a successful update result; public metadata, release link and the exact blue preview PNG were verified. All 98 tests passed in the streaming build environment; packaged GUI/native/codec smoke checks passed. This publication check does not replace subscribed-package testing inside the actual game.

Version **0.8.0-beta.1** is a prerelease for Build 42.21 with singleplayer behavior and experimental multiplayer car audio/shared controls confirmed by two players. Latest volume/tuning fixes, placed radios and dedicated servers still need live testing. Keep those limits explicit in the release and Workshop description.

The packages are separate. The installed game's Workshop validator rejects executable file types, including `.exe` and `.dll`. Never put the connector inside `Contents`. Players download the connector from GitHub and subscribe to the game mod in Workshop.

The existing Workshop item is **3821956623**. Update this item rather than creating another one. Its title is **Muldraugh Afterdark FM [B42.21]** and its description distinguishes singleplayer from the tested scope of the multiplayer beta.

## Build and verify

1. On Windows, run `powershell -ExecutionPolicy Bypass -File .\Build-Release.ps1`.
2. Output is under `dist/0.8.0-beta.1/`: a player ZIP, an EXE for local testing, a Workshop ZIP, an unpacked Workshop folder and SHA-256 checksums.
   If the previous EXE is running, use `.tools/stream-build/Scripts/python.exe tools/build_release.py --output-dir dist/publish-0.8.0-beta.1` to build without interrupting it.
3. The build launches the packaged GUI in hidden smoke-test mode. It validates the Workshop preview size, mod metadata and absence of executable files in `Contents`.
4. Test the EXE with Pear and the mod in a fresh singleplayer world. Check connection/authorization, switching stations, leaving the car, distance volume and clean app shutdown. Automated tests do not replace this check.

## GitHub download

Create a GitHub Release for version `v0.8.0-beta.1` and attach the Windows Connector ZIP and `SHA256SUMS.txt`. The Workshop ZIP is for the author to stage an upload, not for players to execute. Verify the player download before making the Workshop page public. Do not commit built executables or local game files to Git.

Use `docs/releases/v0.8.0-beta.1.md` as the release notes, mark the release as a **prerelease**, and attach `QUICK_START.txt` separately as well. The public checksums should cover the player ZIP and QUICK_START.txt attached to the release; keep author-only Workshop/EXE hashes in the local build output. Download the uploaded ZIP and compare its SHA-256 hash with the local package before announcing it.

The connector ZIP includes the executable, player instructions and runtime notices. Players extract it and double-click the EXE; no separate Python installation or console is required. Keep `docs/QUICK_START.txt` with the download.

## Workshop upload

1. Copy `dist/0.8.0-beta.1/Workshop/MuldraughAfterdarkFM` into your user `Zomboid/Workshop` directory. Its `preview.png`, `workshop.txt` and `Contents` must remain together.
2. In Project Zomboid, use **Workshop → Create and update items**, then select **MuldraughAfterdarkFM**. Review the title, description, preview, tags and game version.
3. On the first upload, start with **Private** visibility. For the existing published item, preserve `id=3821956623` and its current visibility in the generated `workshop.txt`. Never overwrite the ID with the template, which deliberately has no ID.
4. Subscribe and test the actual uploaded package. Remove/disable your local development copy first so it cannot hide mistakes in the Workshop version.
5. Once the connector download and subscribed mod work together, replace the description's release-pending wording with the actual download instructions, review visibility and publish publicly.

The prepared description clearly says the Windows Connector and Pear are required, that multiplayer is a limited beta, and that music selection takes place in Pear. Do not advertise unverified multiplayer scenarios or in-game URL loading.

The build scripts do not upload anything. The existing item can be updated through the in-game uploader or the installed Steam UGC API with the logged-in owning account. Verify the public item metadata, preview and update result after submission. Never create a replacement item or expose Steam/GitHub credentials.

Zomboid can load local mods from the Workshop upload folder too. After publishing, move that folder outside your user Zomboid directory before testing a subscribed copy. Preserve the generated metadata and item ID for the next update; do not install a second local copy with `Install-Mod.ps1` during this check.

# Publishing the Windows companion and Steam Workshop mod

The packages are separate. The installed game's Workshop validator rejects executable file types, including `.exe` and `.dll`. Never put the companion inside `Contents`. Players download the companion from GitHub and subscribe to the game mod in Workshop.

## Build and verify

1. On Windows, run `powershell -ExecutionPolicy Bypass -File .\Build-Release.ps1`.
2. Output is under `dist/0.5.0/`: a player ZIP, an EXE for local testing, a Workshop ZIP, an unpacked Workshop folder and SHA-256 checksums.
3. The build launches the packaged GUI in hidden smoke-test mode. It validates the Workshop preview size, mod metadata and absence of executable files in `Contents`.
4. Test the EXE with Pear and the mod in a fresh singleplayer world. Check connection/authorization, switching stations, leaving the car, distance volume and clean app shutdown. Automated tests do not replace this check.

## GitHub download

Create a GitHub Release for version `v0.5.0` and attach the Windows companion ZIP and `SHA256SUMS.txt`. The Workshop ZIP is for the author to stage an upload, not for players to execute. Verify the player download before making the Workshop page public. Do not commit built executables or local game files to Git.

The companion ZIP includes the executable, player instructions and runtime notices. Players extract it and double-click the EXE; no separate Python installation or console is required. Keep `docs/QUICK_START.txt` with the download.

## Workshop upload

1. Copy `dist/0.5.0/Workshop/MuldraughAfterdarkFM` into your user `Zomboid/Workshop` directory. Its `preview.png`, `workshop.txt` and `Contents` must remain together.
2. In Project Zomboid, use **Workshop → Create and update items**, then select **MuldraughAfterdarkFM**. Review the title, description, preview, tags and game version.
3. Start with **Private** visibility, which is the prepared default. The game creates the Workshop item ID when you upload. Keep its generated `workshop.txt`; do not overwrite that ID on updates.
4. Subscribe and test the actual uploaded package. Remove/disable your local development copy first so it cannot hide mistakes in the Workshop version.
5. Once the companion download and subscribed mod work together, replace the description's release-pending wording with the actual download instructions, review visibility and publish publicly.

The prepared description clearly says the Windows companion and Pear are required, that the mod is singleplayer only, and that music selection takes place in Pear. Never advertise multiplayer or in-game URL loading before those features work.

No Workshop item is uploaded by the build scripts. Uploading and changing visibility happen through your Steam account in the game.

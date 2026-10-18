# Project conventions

- Write source code, identifiers, comments, UI labels, logs, test fixtures, scripts, documentation and commit messages in English.
- Respond to the user in their preferred conversation language.
- Do not add backward-compatibility layers or save migrations during development. When a breaking change requires a fresh save, tell the user to create a new world with the mod. Keep the implementation focused on the current version.
- Verify behavior changes with `python -m unittest discover -s tests -v`. The optional Lua harness uses `lupa` installed under `.tools`; install it with `python -m pip install --target .tools lupa` when needed.
- Keep `.tools`, caches, tokens and local game data out of Git.
- Distinguish automated checks from verification inside the actual game; do not claim multiplayer support until it is implemented and tested.

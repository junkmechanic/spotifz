Fuzzy search songs in your Spotify playlists using [fzf](https://github.com/junegunn/fzf)
in the terminal

[![](/assets/spotifz_demo.gif)](https://junkmechanic.github.io/2019/12/24/searching-in-spotify-playlists-with-fzf/)

# Features

Home Screen:

1. [x] Search Library
2. [x] Current Playback
3. [x] Devices
4. [x] Play/Pause
5. [x] Current Queue
6. [x] Play History
7. [x] Update Cache

Selected Track:

1. [x] Play track in playlist
2. [x] Play track
3. [x] Add to Queue

Selected Play:

1. [x] Play track
2. [x] Add to Queue
3. [x] Play in the playlist or album it was played in

# Installation

1. Make sure you have set up a developer account with Spotify.
2. Create an app on Spotify Dev and obtain the API key.
3. In the app settings, register a redirect URI that matches `redirect_uri` in
   your config _exactly_, including the trailing slash. Spotify no longer
   accepts `localhost`, so use a loopback IP literal with an explicit port,
   e.g. `http://127.0.0.1:8080/`.
4. Copy `config.json` to `~/.config/spotifz.json` and fill in the required json fields.
5. Change to the root directory of this project and run `pip install .`
6. You should be able to call `spotifz` from your shell.
7. Select `Update Cache` the first time you run `spotifz`.

`spotifz` writes two files of its own into `cache_path`, both named after the
`user` in your config: `<user>_spotify.cache.json` holds the OAuth token, and
`<user>_state.json` remembers the playback device you last chose, so you do not
have to pick one every session. Both sit outside `spotify_data/`, which
`Update Cache` deletes and rebuilds.

## Dev Setup

This project uses [uv](https://docs.astral.sh/uv/). It creates a `.venv` in the
project directory and resolves it from the current working directory, so there
is no environment to activate or keep track of.

1. `uv sync` -- creates `.venv` and installs the project with its dev
   dependencies.
2. `uv run spotifz` -- run the CLI from the checkout.
3. `uv run pytest` -- run the test suite.
4. `uv run ruff check .` and `uv run ruff format .` -- lint and format.
5. `uv run pre-commit install` -- optional, to run the hooks on every commit.

`uv.lock` is committed, so `uv sync` installs exactly what it pins. If you
change dependencies in `pyproject.toml`, run `uv lock` and commit the result:
CI runs with `--locked` and fails if the lock and the manifest have drifted
apart. `.python-version` is committed too, so a fresh checkout gets the same
interpreter rather than whichever one happens to satisfy `requires-python`.

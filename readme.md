Fuzzy search songs in your Spotify playlists using [fzf](https://github.com/junegunn/fzf)
in the terminal

[![](/assets/search_demo.gif)](https://junkmechanic.github.io/2019/12/24/searching-in-spotify-playlists-with-fzf/)

# Features

Home Screen:

1. [x] Devices
2. [x] Current Playback
3. [x] Update Cache
4. [x] Play/Pause
5. [x] Search My Library
6. [ ] Current Queue

Selected Track:

1. [x] Play track in playlist
2. [x] Play track

## TODO

- current album in playlist
- play history
- display models for preview
- screen models that store passed args and the previous screen
- current playback to lead to searching by artist, album etc as the input query to fzf
- using a db (perhaps sqlite) instead of json blobs on disk

# Installation

1. Make sure you have set up a developer account with Spotify.
2. Create an app on Spotify Dev and obtain the API key.
3. Copy `config.json` to `~/.config/spotifz.json` and fill in the required json fields.
4. Change to the root directory of this project and run `pip install .`
5. You should be able to call `spotifz` from your shell.
6. Select `Update Cache` the first time you run `spotifz`.

## Dev Setup

1. Create a virtualenv and activate it.
2. `pip install -r requirements.txt`
3. `pip install -e .`

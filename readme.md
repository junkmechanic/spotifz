Find songs in your Spotify playlists

[![](/assets/search_demo.gif)](https://junkmechanic.github.io/)

Features
---
Home Screen:
  1. [x] Devices
  2. [x] Current Playback
  3. [x] Update Cache
  4. [x] Play/Pause
  5. [x] Search My Library
  6. [ ] Current Playlist

Selected Track:
  1. [x] Play track in playlist
  3. [x] Play track

Wishful thinking
---
 - current album in playlist
 - play history
 - display models for preview
 - screen models that store passed args and the previous screen
 - current playback to lead to searching by artist, album etc as the input query to fzf

Dev Setup
---

  1. Make sure you have set up a developer account with Spotify.
  2. Create an app on Spotify Dev and obtain the API key.
  2. Create a virtualenv and activate it.
  3. `pip install -r requirements.txt`
  4. `pip install -e .`
  5. You should be able to call `spotifz` from your shell
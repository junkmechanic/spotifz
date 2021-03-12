import os

from ..helpers import fzf
from .. import spotify


def home_screen(config):
    choices = {
        'Search Library': 'search',
        'Current Playback [!]': 'current_playback',
        'Devices': 'list_devices',
        'Play/Pause': 'resume',
        'Update Cache': 'update_cache',
    }
    chosen = fzf.run_fzf(list(choices.keys()), prompt='[Home] > ')[0]
    if chosen == '':
        return None,
    return choices[chosen],


def list_devices(config):
    sp = spotify.get_spotify_client(config)
    choices = {d['name']: d['id'] for d in sp.devices()['devices']}
    chosen = fzf.run_fzf(list(choices.keys()), prompt='[Devices] > ')[0]
    if chosen == '':
        return 'home_screen',
    # TODO: now that arguments can be passed, could do away with writing to
    # disk
    with open(os.path.join(config['cache_path'], 'device'), 'w') as ofi:
        ofi.write(choices[chosen])
    return 'device_actions',


def device_actions(config):
    with open(os.path.join(config['cache_path'], 'device'), 'r') as ifi:
        device_id = ifi.read()
    sp = spotify.get_spotify_client(config)
    sp.transfer_playback(device_id)
    exit(0)


def resume(config):
    sp = spotify.get_spotify_client(config)
    pb = sp.current_playback()
    if pb['is_playing']:
        sp.pause_playback()
    else:
        sp.start_playback()
    exit(0)


def update_cache(config):
    spotify.update_cache(config)
    return 'home_screen',


def search(config):
    chosen = fzf.run_fzf_sink(spotify.sink_all_tracks, config,
                              prompt='[Search] > ')[0]
    result = list(map(str.strip, chosen.split('::')))
    if len(result) > 1:
        print(result)
        return song_actions(result, config)
    else:
        return 'home_screen',


def song_actions(result, config):
    choices = {
        'Play Song': 'play_song',
        'Play Song in Playlist (not implemented)': 'play_song_in_playlist',
        'Play Album in Playlist (not implemented)': 'play_album_in_playlist',
        'Play Album (not implemented)': 'play_album',
    }

    song_name = result[0]
    if len(song_name) > 20:
        prompt = f'[{song_name[:20]}...] > '
    else:
        prompt = f'[{song_name}] > '

    # TODO: escape singlke quote
    chosen = fzf.run_fzf(list(choices.keys()), prompt=prompt)[0]
    if chosen == '':
        return 'search',
    return choices[chosen], [result[-1], config]


def play_song(config, song_id_and_config):
    song_id = song_id_and_config[0]
    sp = spotify.get_spotify_client(config)
    sp.start_playback(uris=['spotify:track:' + song_id])
    exit(0)

def play_song_in_playlist(config, song_id_and_config):
    return 'home_screen',

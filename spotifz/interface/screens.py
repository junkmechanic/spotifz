from .. import spotify
from ..helpers import fzf


def home_screen(_):
    choices = {
        'Search Library': 'search',
        'Current Playback': 'current_playback',
        'Devices': 'list_devices',
        'Play/Pause': 'resume',
        'Update Cache': 'update_cache',
    }
    chosen = fzf.run_fzf(list(choices.keys()), prompt='[Home] > ')[0]
    if chosen == '':
        return (None,)
    return (choices[chosen],)


def current_playback(config):
    sp = spotify.get_spotify_client(config)
    playback = sp.current_playback()
    if playback is None:
        return ('home_screen',)
    track_name = 'Track : ' + playback['item']['name']
    album = 'Album : ' + playback['item']['album']['name']
    artists = 'Artist : ' + ' ; '.join(
        [artist['name'] for artist in playback['item']['artists']]
    )
    device = 'Device : ' + playback['device']['name']
    fzf.run_fzf([track_name, album, artists, device], prompt='Playback > ')[0]
    return ('home_screen',)


def list_devices(config):
    sp = spotify.get_spotify_client(config)
    choices = {d['name']: d['id'] for d in sp.devices()['devices']}
    chosen = fzf.run_fzf(list(choices.keys()), prompt='[Devices] > ')[0]
    if chosen == '':
        return ('home_screen',)
    return 'device_actions', choices[chosen]


def device_actions(config, device_id):
    """
    For now, there is just one action
    """
    sp = spotify.get_spotify_client(config)
    sp.transfer_playback(device_id)
    config['active_device_id'] = device_id
    if config.get('last_screen') is not None:
        return config.get('last_screen'), *config.get('last_screen_args')
    return ('home_screen',)


def resume(config):
    sp = spotify.get_spotify_client(config)
    playback = sp.current_playback()
    if playback is None:
        if config.get('active_device_id') is None:
            return ('list_devices',)
        sp.start_playback(device_id=config['active_device_id'])
    elif playback['is_playing']:
        sp.pause_playback()
    else:
        sp.start_playback()
    return ('home_screen',)


def update_cache(config):
    spotify.update_cache(config)
    return ('home_screen',)


def search(config):
    chosen = fzf.run_fzf_sink(
        spotify.sink_all_tracks, config, prompt='[Search] > '
    )[0]
    result = list(map(str.strip, chosen.split('::')))
    if len(result) > 1:
        print(result)
        return 'track_actions', result
    else:
        return ('home_screen',)


def track_actions(_, track_props):
    choices = {
        'Play Track in Playlist': 'play_track_in_playlist',
        'Play Track': 'play_track',
    }

    track_name = track_props[0].replace("'", '')
    if len(track_name) > 20:
        prompt = f'[{track_name[:20]}...] > '
    else:
        prompt = f'[{track_name}] > '

    chosen = fzf.run_fzf(list(choices.keys()), prompt=prompt)[0]
    if chosen == '':
        return ('search',)
    return choices[chosen], track_props


def play_track_in_playlist(config, track_props):
    track_id, playlist_id = track_props[-1], track_props[-2]
    sp = spotify.get_spotify_client(config)
    playback = sp.current_playback()
    if playback is None:
        if config.get('active_device_id') is None:
            return ('list_devices',)
        sp.start_playback(device_id=config['active_device_id'])
    sp.start_playback(
        context_uri=f'spotify:playlist:{playlist_id}',
        offset={'uri': f'spotify:track:{track_id}'},
    )
    return ('search',)


def play_track(config, track_props):
    track_id = track_props[-1]
    sp = spotify.get_spotify_client(config)
    sp.start_playback(uris=[f'spotify:track:{track_id}'])
    return ('search',)

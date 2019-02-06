from ..helpers import get_expanded_path, run_fzf
from .. import spotify


def home_screen(config):
    choices = {
        'Search Library': 'search',
        'Current Playback': 'current_playback',
        'Devices': 'list_devices',
        'Update Cache': 'update_cache',
    }
    chosen = run_fzf(list(choices.keys()))[0]
    if chosen == '':
        return None
    return choices[chosen]


def list_devices(config):
    sp = spotify.get_spotify_client(config)
    choices = {d['name']: d['id'] for d in sp.devices()['devices']}
    chosen = run_fzf(list(choices.keys()))[0]
    if chosen == '':
        return 'home_screen'
    with open(get_expanded_path(config['cache_path'], 'device'), 'w') as ofi:
        ofi.write(choices[chosen])
    return 'device_actions'


def device_actions(config):
    # For now, this is just a trigger, and not a selection screen
    with open(get_expanded_path(config['cache_path'], 'device'), 'r') as ifi:
        device_id = ifi.read()
    sp = spotify.get_spotify_client(config)
    sp.transfer_playback(device_id)
    return 'home_screen'

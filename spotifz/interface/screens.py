from collections import Counter

from .. import spotify
from ..helpers import fzf


def _redirect_to_devices(config, screen, *screen_args):
    """
    Send the user to device selection, recording where to return afterwards.
    """
    config['last_screen'] = screen
    config['last_screen_args'] = screen_args
    return ('list_devices',)


def _resolve_device(config, playback):
    """
    Returns the device id to start playback on, or None when the caller should
    redirect to device selection first.
    """
    if playback is not None:
        return playback['device']['id']
    return config.get('active_device_id')


def home_screen(_):
    choices = {
        '[ 1 ] Search Library': 'search',
        '[ 2 ] Current Playback': 'current_playback',
        '[ 3 ] Devices': 'list_devices',
        '[ 4 ] Play/Pause': 'resume',
        '[ 5 ] Update Cache': 'update_cache',
    }
    chosen = fzf.run_fzf(list(choices.keys()), prompt='[Home] > ')[0]
    if chosen == '':
        return (None,)
    return (choices[chosen],)


def describe_playback(playback):
    """
    Builds the display lines for whatever is currently playing. Returns an
    empty list when there is nothing worth showing.
    """
    if playback is None:
        return []

    item = playback.get('item')
    playing_type = playback.get('currently_playing_type')
    device = playback.get('device', {}).get('name')

    if item is None:
        # Adverts carry no item at all. An episode arriving as None means the
        # `additional_types` request parameter did not make it through.
        if playing_type == 'ad':
            lines = ['Playing : advert']
            if device is not None:
                lines.append('Device : ' + device)
            return lines
        return []

    if item.get('type') == 'episode' or item.get('show') is not None:
        # Episodes carry show/publisher rather than album/artists.
        lines = ['Episode : ' + item['name']]
        show = item.get('show') or {}
        if show.get('name'):
            lines.append('Show : ' + show['name'])
        if show.get('publisher'):
            lines.append('Publisher : ' + show['publisher'])
        if item.get('release_date'):
            lines.append('Released : ' + item['release_date'])
    else:
        lines = ['Track : ' + item['name']]
        if item.get('album') is not None:
            lines.append('Album : ' + item['album']['name'])
        if item.get('artists'):
            lines.append(
                'Artist : ' + ' ; '.join(artist['name'] for artist in item['artists'])
            )

    if device is not None:
        lines.append('Device : ' + device)
    return lines


def current_playback(config):
    sp = spotify.get_spotify_client(config)
    # Without `additional_types`, Spotify represents an unsupported item type
    # as a null `item`, so a playing podcast would arrive indistinguishable
    # from an advert and never render.
    playback = sp.current_playback(additional_types='episode')
    lines = describe_playback(playback)
    if not lines:
        return ('home_screen',)

    fzf.run_fzf(lines, prompt='Playback > ')[0]
    return ('home_screen',)


def list_devices(config):
    devices = sp_devices(config)
    chosen = fzf.run_fzf(list(devices.keys()), prompt='[Devices] > ')[0]
    if chosen == '':
        return ('home_screen',)
    return 'device_actions', devices[chosen]


def sp_devices(config):
    """
    Maps a display label to a device id. Device names are not unique (two
    phones, two browsers), so only the colliding ones get disambiguated.
    """
    sp = spotify.get_spotify_client(config)
    devices = sp.devices()['devices']
    name_counts = Counter(d['name'] for d in devices)

    labelled = {}
    for device in devices:
        label = device['name']
        if name_counts[label] > 1:
            label = '{} ({})'.format(label, device['type'])
            # Still ambiguous if the types match too; fall back to the id.
            if label in labelled:
                label = '{} [{}]'.format(label, device['id'][:8])
        labelled[label] = device['id']
    return labelled


def device_actions(config, device_id):
    """
    For now, there is just one action
    """
    sp = spotify.get_spotify_client(config)
    sp.transfer_playback(device_id)
    config['active_device_id'] = device_id
    last_screen = config.pop('last_screen', None)
    if last_screen is not None:
        return last_screen, *config.pop('last_screen_args', ())
    return ('home_screen',)


def resume(config):
    sp = spotify.get_spotify_client(config)
    playback = sp.current_playback()
    if playback is None:
        device_id = _resolve_device(config, playback)
        if device_id is None:
            return _redirect_to_devices(config, 'resume')
        sp.start_playback(device_id=device_id)
    elif playback['is_playing']:
        sp.pause_playback()
    else:
        sp.start_playback()
    return ('home_screen',)


def update_cache(config):
    spotify.update_cache(config)
    return ('home_screen',)


def search(config):
    chosen = fzf.run_fzf_sink(spotify.sink_all_tracks, config, prompt='[Search] > ')[0]
    result = list(map(str.strip, chosen.split('::')))
    if len(result) > 1:
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
    device_id = _resolve_device(config, sp.current_playback())
    if device_id is None:
        return _redirect_to_devices(config, 'play_track_in_playlist', track_props)
    sp.start_playback(
        device_id=device_id,
        context_uri=f'spotify:playlist:{playlist_id}',
        offset={'uri': f'spotify:track:{track_id}'},
    )
    return ('search',)


def play_track(config, track_props):
    track_id = track_props[-1]
    sp = spotify.get_spotify_client(config)
    device_id = _resolve_device(config, sp.current_playback())
    if device_id is None:
        return _redirect_to_devices(config, 'play_track', track_props)
    sp.start_playback(device_id=device_id, uris=[f'spotify:track:{track_id}'])
    return ('search',)

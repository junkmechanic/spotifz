from collections import Counter

from spotipy import SpotifyException

from .. import spotify
from ..helpers import fzf


def _redirect_to_devices(state, screen, *screen_args):
    """
    Send the user to device selection, recording where to return afterwards.
    """
    state.pending_screen = (screen, screen_args)
    return ('list_devices',)


def _resolve_device(state, playback):
    """
    Returns the device id to start playback on, or None when the caller should
    redirect to device selection first.
    """
    if playback is not None:
        return playback['device']['id']
    return state.active_device_id


def _player_command(state, command, **kwargs):
    """
    Runs one command against the player. A device that was alive last session
    may be gone this one, and Spotify answers with a 404. Forget it, so the
    caller can send the user to pick another -- the same path as never having
    chosen one.
    """
    try:
        command(**kwargs)
    except SpotifyException:
        state.forget_active_device()
        return False
    return True


# Menu label -> the screen it dispatches to. Module-level rather than local so
# a test can check every destination against the registry: a misspelled name
# here would otherwise only surface as a failed lookup after fzf has exited.
HOME_CHOICES = {
    '[ 1 ] Search Library': 'search',
    '[ 2 ] Current Playback': 'current_playback',
    '[ 3 ] Devices': 'list_devices',
    '[ 4 ] Play/Pause': 'resume',
    '[ 5 ] Update Cache': 'update_cache',
    '[ 6 ] Current Queue': 'current_queue',
}

TRACK_ACTIONS_CHOICES = {
    'Play Track in Playlist': 'play_track_in_playlist',
    'Play Track': 'play_track',
    'Add to Queue': 'add_to_queue',
}


def home_screen(_):
    chosen = fzf.run_fzf(list(HOME_CHOICES.keys()), prompt='[Home] > ')[0]
    if chosen == '':
        return (None,)
    return (HOME_CHOICES[chosen],)


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


# 'Now' is the widest marker the numbered rows line up against.
QUEUE_NOW = 'Now'
UNKNOWN_ITEM = 'unknown item'


def _one_line(value):
    """
    run_fzf joins the candidates with newlines, so a name carrying one would
    arrive as a row of its own.
    """
    return ' '.join(str(value if value is not None else '').split())


def _artist_names(item):
    names = (_one_line(artist.get('name')) for artist in item.get('artists') or [])
    return ', '.join(name for name in names if name)


def describe_queue_item(item):
    """
    One queued item, read in the same order as a search result: what it is,
    what it came from, who made it.
    """
    if item.get('type') == 'episode' or item.get('show') is not None:
        # Episodes carry show/publisher rather than album/artists.
        show = item.get('show') or {}
        parts = [item.get('name'), show.get('name'), show.get('publisher')]
    else:
        parts = [
            item.get('name'),
            (item.get('album') or {}).get('name'),
            _artist_names(item),
        ]
    row = spotify.DISPLAY_SEPARATOR.join(part for part in map(_one_line, parts) if part)
    # A row naming nothing at all still occupies a numbered slot, so it says so
    # rather than trailing off after the number.
    return row or UNKNOWN_ITEM


def describe_queue(queue):
    """
    Builds the display rows for the queue: what is playing now, then what
    follows it, in order. Returns an empty list when there is nothing to show.
    """
    if not queue:
        # With no active device Spotify answers 204, which arrives as None:
        # there is no queue, rather than an empty one.
        return []

    rows = []
    now_playing = queue.get('currently_playing')
    if now_playing is not None:
        rows.append((QUEUE_NOW, now_playing))
    # Numbered over the items that survive, so a marker is a position in the
    # list on screen and the count never skips.
    upcoming = [item for item in queue.get('queue') or [] if item is not None]
    rows.extend((str(position), item) for position, item in enumerate(upcoming, 1))
    if not rows:
        return []

    marker_width = max(len(marker) for marker, _ in rows)
    return [
        '{}  {}'.format(marker.rjust(marker_width), describe_queue_item(item))
        for marker, item in rows
    ]


def current_playback(state):
    sp = spotify.get_spotify_client(state.config)
    # Without `additional_types`, Spotify represents an unsupported item type
    # as a null `item`, so a playing podcast would arrive indistinguishable
    # from an advert and never render.
    playback = sp.current_playback(additional_types='episode')
    lines = describe_playback(playback)
    if not lines:
        return ('home_screen',)

    fzf.run_fzf(lines, prompt='Playback > ')[0]
    return ('home_screen',)


def current_queue(state):
    """
    Read-only: Spotify can append to the queue and skip one track at a time,
    but has no way to jump to a chosen position in it, so there is nothing
    honest for a selection here to do.
    """
    sp = spotify.get_spotify_client(state.config)
    rows = describe_queue(sp.queue())
    if not rows:
        return ('home_screen',)

    fzf.run_fzf(rows, prompt='[Queue] > ')
    return ('home_screen',)


def list_devices(state):
    devices = sp_devices(state)
    chosen = fzf.run_fzf(list(devices.keys()), prompt='[Devices] > ')[0]
    if chosen == '':
        return ('home_screen',)
    return 'device_actions', devices[chosen]


def sp_devices(state):
    """
    Maps a display label to a device id. Device names are not unique (two
    phones, two browsers), so only the colliding ones get disambiguated.
    """
    sp = spotify.get_spotify_client(state.config)
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


def device_actions(state, device_id):
    """
    For now, there is just one action
    """
    sp = spotify.get_spotify_client(state.config)
    sp.transfer_playback(device_id)
    state.set_active_device(device_id)
    pending = state.take_pending_screen()
    if pending is not None:
        screen, screen_args = pending
        return (screen, *screen_args)
    return ('home_screen',)


def resume(state):
    sp = spotify.get_spotify_client(state.config)
    playback = sp.current_playback()
    if playback is None:
        device_id = _resolve_device(state, playback)
        started = device_id is not None and _player_command(
            state, sp.start_playback, device_id=device_id
        )
        if not started:
            return _redirect_to_devices(state, 'resume')
    elif playback['is_playing']:
        sp.pause_playback()
    else:
        sp.start_playback()
    return ('home_screen',)


def update_cache(state):
    spotify.update_cache(state.config)
    return ('home_screen',)


def search(state):
    chosen = fzf.run_fzf_sink(
        spotify.sink_all_tracks, state.config, prompt='[Search] > '
    )[0]
    # An empty selection -- the user hit Esc -- carries no separator.
    if spotify.SEPARATOR not in chosen:
        return ('home_screen',)
    return 'track_actions', spotify.parse_track_line(chosen)


def track_actions(_, track):
    track_name = track.name.replace("'", '')
    if len(track_name) > 20:
        prompt = f'[{track_name[:20]}...] > '
    else:
        prompt = f'[{track_name}] > '

    chosen = fzf.run_fzf(list(TRACK_ACTIONS_CHOICES.keys()), prompt=prompt)[0]
    if chosen == '':
        return ('search',)
    return TRACK_ACTIONS_CHOICES[chosen], track


def play_track_in_playlist(state, track):
    sp = spotify.get_spotify_client(state.config)
    device_id = _resolve_device(state, sp.current_playback())
    started = device_id is not None and _player_command(
        state,
        sp.start_playback,
        device_id=device_id,
        context_uri=f'spotify:playlist:{track.playlist_id}',
        offset={'uri': f'spotify:track:{track.track_id}'},
    )
    if not started:
        return _redirect_to_devices(state, 'play_track_in_playlist', track)
    return ('search',)


def play_track(state, track):
    sp = spotify.get_spotify_client(state.config)
    device_id = _resolve_device(state, sp.current_playback())
    started = device_id is not None and _player_command(
        state,
        sp.start_playback,
        device_id=device_id,
        uris=[f'spotify:track:{track.track_id}'],
    )
    if not started:
        return _redirect_to_devices(state, 'play_track', track)
    return ('search',)


def add_to_queue(state, track):
    """
    Appends to the queue, so tracks can be stacked one after another without
    leaving the results -- which is why this returns to the search.
    """
    sp = spotify.get_spotify_client(state.config)
    device_id = _resolve_device(state, sp.current_playback())
    queued = device_id is not None and _player_command(
        state,
        sp.add_to_queue,
        uri=f'spotify:track:{track.track_id}',
        device_id=device_id,
    )
    if not queued:
        return _redirect_to_devices(state, 'add_to_queue', track)
    return ('search',)

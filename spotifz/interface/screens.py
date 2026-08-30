from collections import Counter
from datetime import datetime, timezone

from spotipy import SpotifyException

from .. import spotify
from ..helpers import fzf


class UnknownScreen(LookupError):
    """
    A screen returned a name nothing is registered under. Always a bug in this
    repo -- a screen name is never user input and is never read from disk -- so
    it is deliberately not caught in cli.main, which would swallow the
    traceback that says which name. LookupError rather than KeyError, whose
    __str__ reprs the message and would print it wrapped in quotes.
    """


# Name -> screen. Registration is an import side effect, which is why the
# registry lives beside the screens rather than in a module of its own: a
# separate module could be imported before them and answer lookups from a
# legitimately empty dict.
SCREENS = {}


def screen(fn):
    """
    Marks a function as reachable as a destination from another screen. The
    key is the function's own name, so the strings the screens already return
    stay the contract and cannot drift from the definitions.
    """
    SCREENS[fn.__name__] = fn
    return fn


def get_screen(name):
    try:
        return SCREENS[name]
    except KeyError:
        raise UnknownScreen(
            '{!r} is not a registered screen. Screens are the functions '
            'decorated with @screen in {}.'.format(name, __name__)
        ) from None


def _redirect_to_devices(state, screen_name, *screen_args):
    """
    Send the user to device selection, recording where to return afterwards.
    """
    state.pending_screen = (screen_name, screen_args)
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
    '[ 5 ] Current Queue': 'current_queue',
    '[ 6 ] Play History': 'play_history',
    # Last: the one entry that is maintenance rather than playback, and the
    # only one that goes away and rebuilds the library before it returns.
    '[ 7 ] Update Cache': 'update_cache',
}

TRACK_ACTIONS_CHOICES = {
    'Play Track in Playlist': 'play_track_in_context',
    'Play Track': 'play_track',
    'Add to Queue': 'add_to_queue',
}

# What a track picked out of the play history can do without knowing anything
# about where it was played. Resuming the context it came from is offered on
# top of these, and only when there is one worth resuming, so it cannot be a
# fixed entry here.
HISTORY_ACTIONS_CHOICES = {
    'Play Track': 'play_track',
    'Add to Queue': 'add_to_queue',
}


@screen
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


def _track_prompt(track_name):
    """
    The prompt for a menu about one track. Long names are truncated so the
    prompt does not push the choices off the line.
    """
    track_name = track_name.replace("'", '')
    if len(track_name) > 20:
        return f'[{track_name[:20]}...] > '
    return f'[{track_name}] > '


def _artist_names(item):
    names = (_one_line(artist.get('name')) for artist in item.get('artists') or [])
    return ', '.join(name for name in names if name)


def describe_item(item):
    """
    One track or episode as a row, read in the same order as a search result:
    what it is, what it came from, who made it. Shared by every screen that
    lists items rather than describing one.
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
        '{}  {}'.format(marker.rjust(marker_width), describe_item(item))
        for marker, item in rows
    ]


# Spotify sends `2026-08-29T21:14:03.123Z`. datetime.fromisoformat only accepts
# that trailing Z from 3.11, and this package supports 3.9, so the fixed prefix
# is parsed instead -- which is indifferent to the Z and to how many fractional
# digits came with it.
PLAYED_AT_FORMAT = '%Y-%m-%dT%H:%M:%S'
PLAYED_AT_LENGTH = 19


def _parse_played_at(played_at):
    try:
        parsed = datetime.strptime(played_at[:PLAYED_AT_LENGTH], PLAYED_AT_FORMAT)
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc)


def played_ago(played_at, now):
    """
    How long ago, compactly. Empty for a timestamp that will not parse, so a
    row that Spotify described oddly loses its suffix rather than the screen.
    """
    parsed = _parse_played_at(played_at)
    if parsed is None:
        return ''

    seconds = (now - parsed).total_seconds()
    if seconds < 0:
        # Clock skew between here and Spotify. 'in 3 minutes' would be absurd
        # on a history, so the newest row just reads as the newest.
        return 'just now'
    minutes, hours, days = seconds // 60, seconds // 3600, seconds // 86400
    if minutes < 1:
        return 'just now'
    if hours < 1:
        return '{:.0f}m ago'.format(minutes)
    if days < 1:
        return '{:.0f}h ago'.format(hours)
    if days < 2:
        return 'yesterday'
    return '{:.0f}d ago'.format(days)


def current_time():
    """
    Exists to be replaceable. The relative times on the history rows are read
    against this, and a test that cannot hold it still would be asserting
    against the wall clock.
    """
    return datetime.now(timezone.utc)


def describe_history_item(entry):
    """
    One play as a row. Only a playlist is named: an album is already the row's
    second field, and an artist or Liked Songs adds nothing the row does not
    carry -- though both are still named on the entry, for the action menu that
    offers to resume them.
    """
    row = describe_item(entry.track)
    if entry.context_type == 'playlist' and entry.context_name:
        row += spotify.DISPLAY_SEPARATOR + _one_line(entry.context_name)
    return row


def describe_history(entries, now):
    """
    Builds the display rows for the play history, newest first as Spotify
    returns it. Numbered the way the queue is: the number is a position on
    screen, and it is also what keeps two plays of the same track from
    rendering as the same row.
    """
    if not entries:
        return []

    marker_width = len(str(len(entries)))
    rows = []
    for position, entry in enumerate(entries, 1):
        row = '{}  {}'.format(
            str(position).rjust(marker_width), describe_history_item(entry)
        )
        ago = played_ago(entry.played_at, now)
        if ago:
            row += '  ({})'.format(ago)
        rows.append(row)
    return rows


@screen
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


@screen
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


@screen
def play_history(state):
    """
    What Spotify recorded as recently played -- tracks only, newest first, one
    row per play rather than per track, since playing something three times is
    the interesting part of a history.
    """
    sp = spotify.get_spotify_client(state.config)
    response = sp.current_user_recently_played()
    playlist_names = spotify.read_playlist_names(
        state.config, spotify.history_playlist_ids(response)
    )
    entries = spotify.history_entries(response, playlist_names)
    rows = describe_history(entries, current_time())
    if not rows:
        return ('home_screen',)

    chosen = fzf.run_fzf(rows, prompt='[History] > ')[0]
    # Row -> entry, the way list_devices maps a label back to a device. The
    # position each row is numbered with is what makes the keys unique.
    entry = dict(zip(rows, entries)).get(chosen)
    if entry is None:
        return ('home_screen',)
    return 'history_actions', entry


@screen
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


@screen
def device_actions(state, device_id):
    """
    For now, there is just one action
    """
    sp = spotify.get_spotify_client(state.config)
    sp.transfer_playback(device_id)
    state.set_active_device(device_id)
    pending = state.take_pending_screen()
    if pending is not None:
        screen_name, screen_args = pending
        return (screen_name, *screen_args)
    return ('home_screen',)


@screen
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


@screen
def update_cache(state):
    spotify.update_cache(state.config)
    return ('home_screen',)


@screen
def search(state):
    chosen = fzf.run_fzf_sink(
        spotify.sink_all_tracks, state.config, prompt='[Search] > '
    )[0]
    # An empty selection -- the user hit Esc -- carries no separator.
    if spotify.SEPARATOR not in chosen:
        return ('home_screen',)
    return 'track_actions', spotify.parse_track_line(chosen), 'search'


def context_action_label(entry):
    """
    The label for resuming what a track was played inside, or None when there
    is nothing to resume. A playlist that was never cached has no name to offer
    but is still worth offering, since the action needs only the uri.
    """
    if not entry.is_resumable:
        return None
    if entry.context_name:
        return 'Play in {}'.format(_one_line(entry.context_name))
    return 'Play in {}'.format(entry.context_type.capitalize())


@screen
def history_actions(_, entry):
    """
    Everything here is already on the entry, so opening this menu costs no
    request -- which is what naming the context when the rows were built buys.
    """
    choices = dict(HISTORY_ACTIONS_CHOICES)
    context_label = context_action_label(entry)
    if context_label is not None:
        choices[context_label] = 'play_track_in_context'

    chosen = fzf.run_fzf(list(choices.keys()), prompt=_track_prompt(entry.name))[0]
    if chosen == '':
        return ('play_history',)
    return choices[chosen], entry, 'play_history'


@screen
def track_actions(_, track, origin):
    """
    `origin` is the screen the track was picked on, carried through every
    action below so each of them returns where the user actually was. Spelled
    out at each call site rather than defaulted, so a new caller has to say
    where it came from instead of silently inheriting the search.
    """
    chosen = fzf.run_fzf(
        list(TRACK_ACTIONS_CHOICES.keys()), prompt=_track_prompt(track.name)
    )[0]
    if chosen == '':
        return (origin,)
    return TRACK_ACTIONS_CHOICES[chosen], track, origin


@screen
def play_track_in_context(state, track, origin):
    """
    Plays the track inside whatever it was found in, so what follows it is the
    rest of that playlist or album rather than nothing. `offset` is what starts
    the context at this track, and Spotify accepts it only for a playlist or an
    album -- which is why callers that hold some other kind of context do not
    route here.
    """
    sp = spotify.get_spotify_client(state.config)
    device_id = _resolve_device(state, sp.current_playback())
    started = device_id is not None and _player_command(
        state,
        sp.start_playback,
        device_id=device_id,
        context_uri=track.context_uri,
        offset={'uri': f'spotify:track:{track.track_id}'},
    )
    if not started:
        return _redirect_to_devices(state, 'play_track_in_context', track, origin)
    return (origin,)


@screen
def play_track(state, track, origin):
    sp = spotify.get_spotify_client(state.config)
    device_id = _resolve_device(state, sp.current_playback())
    started = device_id is not None and _player_command(
        state,
        sp.start_playback,
        device_id=device_id,
        uris=[f'spotify:track:{track.track_id}'],
    )
    if not started:
        return _redirect_to_devices(state, 'play_track', track, origin)
    return (origin,)


@screen
def add_to_queue(state, track, origin):
    """
    Appends to the queue, so tracks can be stacked one after another without
    leaving the list they were picked from -- which is why this returns there.
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
        return _redirect_to_devices(state, 'add_to_queue', track, origin)
    return (origin,)

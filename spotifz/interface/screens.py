from collections import Counter
from datetime import datetime, timezone
from typing import NamedTuple, Optional

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
    '[ 5 ] Update Cache': 'update_cache',
    '[ 6 ] Current Queue': 'current_queue',
}

TRACK_ACTIONS_CHOICES = {
    'Play Track in Playlist': 'play_track_in_context',
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


# Contexts a track can be resumed *inside*. Spotify accepts the `offset` that
# starts a context at a chosen track only for these two, so an artist or a
# Liked Songs context would start somewhere the user did not pick.
RESUMABLE_CONTEXTS = ('playlist', 'album')
PLAYLIST_URI_PREFIX = 'spotify:playlist:'


class HistoryEntry(NamedTuple):
    """
    One play out of the history. `track_id` and `name` are spelled the way
    TrackRef spells them, which is what lets play_track and add_to_queue take
    an entry without knowing which list it was picked from.
    """

    display: str
    track_id: str
    context_uri: Optional[str]
    context_type: Optional[str]
    context_name: Optional[str]
    played_at: str

    @property
    def name(self):
        # Cosmetic, for the fzf prompt only, as on TrackRef.
        return self.display.split(spotify.DISPLAY_SEPARATOR)[0]

    @property
    def is_resumable(self):
        return self.context_uri is not None and self.context_type in RESUMABLE_CONTEXTS


def context_playlist_id(context):
    """
    The playlist id out of a context, or None for a context that is not a
    playlist -- an album, an artist, Liked Songs, or no context at all, which
    is what a track played from a radio or from search arrives with.
    """
    uri = (context or {}).get('uri') or ''
    if not uri.startswith(PLAYLIST_URI_PREFIX):
        return None
    return uri[len(PLAYLIST_URI_PREFIX) :] or None


def history_entries(response, playlist_names=None):
    """
    Maps the recently-played response onto entries. `playlist_names` is handed
    in rather than read here, so this stays a pure function of the response and
    the caller owns the one cache read.
    """
    playlist_names = playlist_names or {}
    entries = []
    for item in (response or {}).get('items') or []:
        track = (item or {}).get('track')
        if not track:
            continue
        context = item.get('context') or None
        playlist_id = context_playlist_id(context)
        # Only a playlist is named on the row: an album is already the row's
        # second field, and an artist or Liked Songs adds nothing the row does
        # not carry.
        context_name = playlist_names.get(playlist_id) if playlist_id else None

        display = describe_item(track)
        if context_name:
            display += spotify.DISPLAY_SEPARATOR + _one_line(context_name)
        entries.append(
            HistoryEntry(
                display=display,
                track_id=track.get('id'),
                context_uri=(context or {}).get('uri'),
                context_type=(context or {}).get('type'),
                context_name=context_name,
                played_at=item.get('played_at') or '',
            )
        )
    return entries


def history_playlist_ids(response):
    """The playlist ids a response refers to, for the caller's cache read."""
    ids = (
        context_playlist_id((item or {}).get('context'))
        for item in (response or {}).get('items') or []
    )
    return [playlist_id for playlist_id in ids if playlist_id]


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
        row = '{}  {}'.format(str(position).rjust(marker_width), entry.display)
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


@screen
def track_actions(_, track, origin):
    """
    `origin` is the screen the track was picked on, carried through every
    action below so each of them returns where the user actually was. Spelled
    out at each call site rather than defaulted, so a new caller has to say
    where it came from instead of silently inheriting the search.
    """
    track_name = track.name.replace("'", '')
    if len(track_name) > 20:
        prompt = f'[{track_name[:20]}...] > '
    else:
        prompt = f'[{track_name}] > '

    chosen = fzf.run_fzf(list(TRACK_ACTIONS_CHOICES.keys()), prompt=prompt)[0]
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

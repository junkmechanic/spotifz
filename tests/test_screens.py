import pytest
from spotipy import SpotifyException

from spotifz.interface import screens
from spotifz.spotify.sink import SEPARATOR, TrackRef
from spotifz.state import AppState


def track_ref(display, track_id='track-1', playlist_id='pl-1'):
    """
    A TrackRef with the pair fields filled in. The screens below never read
    playlist_name or added_at -- those exist for the preview pane -- so naming
    them at every call site would be noise.
    """
    return TrackRef(display, track_id, playlist_id, 'Road Trip', '2019-04-03T10:00:00Z')


class FakeClient:
    def __init__(self, playback=None, devices=(), start_error=None):
        self._playback = playback
        self._devices = list(devices)
        self._start_error = start_error
        self.calls = []

    def current_playback(self, **kwargs):
        self.calls.append(('current_playback', kwargs))
        return self._playback

    def devices(self):
        self.calls.append(('devices', {}))
        return {'devices': self._devices}

    def transfer_playback(self, device_id):
        self.calls.append(('transfer_playback', device_id))

    def start_playback(self, **kwargs):
        self.calls.append(('start_playback', kwargs))
        if self._start_error is not None:
            raise self._start_error

    def pause_playback(self):
        self.calls.append(('pause_playback', {}))

    def named(self, name):
        return [call for call in self.calls if call[0] == name]


@pytest.fixture
def client(monkeypatch):
    """
    Installs a fake Spotify client. Every screen reaches the client through
    screens.spotify.get_spotify_client, so that is the only seam needed.
    """

    def _install(playback=None, devices=(), start_error=None):
        fake = FakeClient(playback, devices, start_error)
        monkeypatch.setattr(screens.spotify, 'get_spotify_client', lambda cfg: fake)
        return fake

    return _install


@pytest.fixture
def fzf(monkeypatch):
    """Scripts run_fzf's selections and records what it was shown."""
    seen = {'prompts': [], 'items': []}

    def _install(*selections):
        queue = list(selections)

        def _run_fzf(items, prompt=None):
            seen['prompts'].append(prompt)
            seen['items'].append(items)
            return [queue.pop(0) if queue else '']

        monkeypatch.setattr(screens.fzf, 'run_fzf', _run_fzf)
        return seen

    return _install


def track_playback(name='Song', album='Album', artists=('A', 'B'), device='Laptop'):
    return {
        'is_playing': True,
        'currently_playing_type': 'track',
        'device': {'id': 'device-1', 'name': device},
        'item': {
            'type': 'track',
            'name': name,
            'album': {'name': album},
            'artists': [{'name': artist} for artist in artists],
        },
    }


# --- describe_playback -------------------------------------------------------


def test_describe_playback_says_nothing_when_nothing_is_playing():
    assert screens.describe_playback(None) == []


def test_describe_playback_renders_a_track():
    assert screens.describe_playback(track_playback()) == [
        'Track : Song',
        'Album : Album',
        'Artist : A ; B',
        'Device : Laptop',
    ]


def test_describe_playback_omits_a_missing_album():
    playback = track_playback()
    playback['item']['album'] = None

    assert 'Album : ' not in ' '.join(screens.describe_playback(playback))


def test_describe_playback_omits_empty_artists():
    playback = track_playback()
    playback['item']['artists'] = []

    assert screens.describe_playback(playback) == [
        'Track : Song',
        'Album : Album',
        'Device : Laptop',
    ]


def test_describe_playback_renders_an_episode():
    playback = {
        'currently_playing_type': 'episode',
        'device': {'name': 'Phone'},
        'item': {
            'type': 'episode',
            'name': 'Episode One',
            'show': {'name': 'The Show', 'publisher': 'A Publisher'},
            'release_date': '2026-01-01',
        },
    }

    assert screens.describe_playback(playback) == [
        'Episode : Episode One',
        'Show : The Show',
        'Publisher : A Publisher',
        'Released : 2026-01-01',
        'Device : Phone',
    ]


def test_describe_playback_recognises_an_episode_by_its_show_alone():
    """Not every episode payload carries type == 'episode'."""
    playback = {
        'device': {'name': 'Phone'},
        'item': {'name': 'Episode One', 'show': {'name': 'The Show'}},
    }

    lines = screens.describe_playback(playback)

    assert lines[0] == 'Episode : Episode One'
    assert 'Show : The Show' in lines


def test_describe_playback_renders_an_advert():
    """Adverts arrive with no item at all."""
    playback = {
        'currently_playing_type': 'ad',
        'device': {'name': 'Laptop'},
        'item': None,
    }

    assert screens.describe_playback(playback) == [
        'Playing : advert',
        'Device : Laptop',
    ]


def test_describe_playback_ignores_an_itemless_response_that_is_not_an_advert():
    playback = {'currently_playing_type': 'track', 'item': None}

    assert screens.describe_playback(playback) == []


def test_describe_playback_omits_a_missing_device():
    playback = track_playback()
    del playback['device']

    assert screens.describe_playback(playback) == [
        'Track : Song',
        'Album : Album',
        'Artist : A ; B',
    ]


def queue_item(name='Song', album='Album', artists=('A', 'B')):
    return {
        'type': 'track',
        'name': name,
        'album': {'name': album},
        'artists': [{'name': artist} for artist in artists],
    }


# --- describe_queue ----------------------------------------------------------


def test_describe_queue_says_nothing_without_a_queue():
    """No active device answers 204, which spotipy hands back as None."""
    assert screens.describe_queue(None) == []


def test_describe_queue_says_nothing_when_the_queue_is_empty():
    assert screens.describe_queue({'currently_playing': None, 'queue': []}) == []


def test_describe_queue_marks_what_is_playing_and_numbers_what_follows():
    queue = {
        'currently_playing': queue_item('Song A'),
        'queue': [queue_item('Song B'), queue_item('Song C')],
    }

    assert screens.describe_queue(queue) == [
        'Now  Song A :: Album :: A, B',
        '  1  Song B :: Album :: A, B',
        '  2  Song C :: Album :: A, B',
    ]


def test_describe_queue_numbers_from_one_when_nothing_is_playing():
    queue = {'currently_playing': None, 'queue': [queue_item('Song B')]}

    assert screens.describe_queue(queue) == ['1  Song B :: Album :: A, B']


def test_describe_queue_lines_up_two_digit_positions():
    """
    The markers are a column, not a prefix: ragged numbers push every title to
    a different indent and the pane stops being scannable.
    """
    queue = {'currently_playing': None, 'queue': [queue_item() for _ in range(10)]}

    rows = screens.describe_queue(queue)

    assert rows[0].startswith(' 1  Song')
    assert rows[9].startswith('10  Song')


def test_describe_queue_renders_an_episode():
    queue = {
        'currently_playing': None,
        'queue': [
            {
                'type': 'episode',
                'name': 'Episode One',
                'show': {'name': 'The Show', 'publisher': 'A Publisher'},
            }
        ],
    }

    assert screens.describe_queue(queue) == ['1  Episode One :: The Show :: A Publisher']


def test_describe_queue_recognises_an_episode_by_its_show_alone():
    """Not every episode payload carries type == 'episode'."""
    item = {'name': 'Episode One', 'show': {'name': 'The Show'}}

    assert screens.describe_queue_item(item) == 'Episode One :: The Show'


def test_describe_queue_omits_a_missing_album_and_artists():
    item = {'type': 'track', 'name': 'Song', 'album': None, 'artists': []}

    assert screens.describe_queue_item(item) == 'Song'


def test_describe_queue_names_an_item_it_cannot_describe():
    """The row still holds a numbered slot, so it may not trail off blank."""
    assert screens.describe_queue_item({'type': 'track'}) == 'unknown item'


def test_describe_queue_keeps_one_item_on_one_row():
    """
    run_fzf joins the candidates with newlines, so a name carrying one would
    otherwise arrive as an extra row that selects nothing.
    """
    queue = {'currently_playing': None, 'queue': [queue_item('Song\nB')]}

    rows = screens.describe_queue(queue)

    assert rows == ['1  Song B :: Album :: A, B']


def test_describe_queue_does_not_skip_a_number_for_an_unrenderable_entry():
    """An advert in the queue arrives as a null entry."""
    queue = {
        'currently_playing': None,
        'queue': [queue_item('Song A'), None, queue_item('Song C')],
    }

    rows = screens.describe_queue(queue)

    assert [row.split('  ')[0] for row in rows] == ['1', '2']
    assert rows[1].endswith('Song C :: Album :: A, B')


# --- current_playback --------------------------------------------------------


def test_current_playback_asks_for_episodes(state, client, fzf):
    """
    Without additional_types a playing podcast comes back as a null item,
    indistinguishable from an advert, and never renders.
    """
    fake = client(playback=track_playback())
    fzf('Track : Song')

    screens.current_playback(state)

    assert fake.named('current_playback')[0][1] == {'additional_types': 'episode'}


def test_current_playback_returns_home_without_prompting(state, client, fzf):
    client(playback=None)
    seen = fzf()

    assert screens.current_playback(state) == ('home_screen',)
    assert seen['items'] == []


def test_current_playback_shows_the_lines(state, client, fzf):
    client(playback=track_playback())
    seen = fzf('Track : Song')

    assert screens.current_playback(state) == ('home_screen',)
    assert seen['items'][0][0] == 'Track : Song'


# --- devices -----------------------------------------------------------------


def test_sp_devices_leaves_unique_names_alone(state, client):
    client(
        devices=[
            {'id': 'd1', 'name': 'Laptop', 'type': 'Computer'},
            {'id': 'd2', 'name': 'Phone', 'type': 'Smartphone'},
        ]
    )

    assert screens.sp_devices(state) == {'Laptop': 'd1', 'Phone': 'd2'}


def test_sp_devices_disambiguates_duplicate_names_by_type(state, client):
    """
    Two devices sharing a name would otherwise collapse into one dict entry and
    the second would be unreachable.
    """
    client(
        devices=[
            {'id': 'd1', 'name': 'Chrome', 'type': 'Computer'},
            {'id': 'd2', 'name': 'Chrome', 'type': 'Smartphone'},
        ]
    )

    assert screens.sp_devices(state) == {
        'Chrome (Computer)': 'd1',
        'Chrome (Smartphone)': 'd2',
    }


def test_sp_devices_falls_back_to_the_id_when_the_type_also_collides(state, client):
    client(
        devices=[
            {'id': 'aaaaaaaaaa', 'name': 'Chrome', 'type': 'Computer'},
            {'id': 'bbbbbbbbbb', 'name': 'Chrome', 'type': 'Computer'},
        ]
    )

    labelled = screens.sp_devices(state)

    assert sorted(labelled.values()) == ['aaaaaaaaaa', 'bbbbbbbbbb']
    assert 'Chrome (Computer) [bbbbbbbb]' in labelled


def test_list_devices_returns_home_on_an_empty_selection(state, client, fzf):
    client(devices=[{'id': 'd1', 'name': 'Laptop', 'type': 'Computer'}])
    fzf('')

    assert screens.list_devices(state) == ('home_screen',)


def test_list_devices_hands_the_id_to_device_actions(state, client, fzf):
    client(devices=[{'id': 'd1', 'name': 'Laptop', 'type': 'Computer'}])
    fzf('Laptop')

    assert screens.list_devices(state) == ('device_actions', 'd1')


def test_device_actions_transfers_playback_and_records_the_device(state, client):
    fake = client()

    assert screens.device_actions(state, 'd1') == ('home_screen',)
    assert fake.named('transfer_playback') == [('transfer_playback', 'd1')]
    assert state.active_device_id == 'd1'
    # Persisted, not just remembered: a later session finds the same device.
    assert AppState.from_config(state.config).active_device_id == 'd1'


# --- home_screen -------------------------------------------------------------


def test_home_screen_maps_the_label_to_a_screen(state, fzf):
    fzf('[ 1 ] Search Library')

    assert screens.home_screen(state) == ('search',)


def test_home_screen_exits_on_an_empty_selection(state, fzf):
    fzf('')

    assert screens.home_screen(state) == (None,)


# --- resume ------------------------------------------------------------------


def test_resume_pauses_what_is_playing(state, client):
    fake = client(playback=track_playback())

    assert screens.resume(state) == ('home_screen',)
    assert fake.named('pause_playback')
    assert fake.named('start_playback') == []


def test_resume_restarts_a_paused_playback(state, client):
    playback = track_playback()
    playback['is_playing'] = False
    fake = client(playback=playback)

    screens.resume(state)

    # Playback already has a device, so no device_id is needed.
    assert fake.named('start_playback') == [('start_playback', {})]


def test_resume_redirects_to_devices_without_a_playback_or_active_device(state, client):
    fake = client(playback=None)

    assert screens.resume(state) == ('list_devices',)
    assert fake.named('start_playback') == []
    assert state.pending_screen == ('resume', ())


def test_resume_starts_on_the_active_device_with_a_single_call(state, client):
    """
    The device id has to travel on the same start_playback call. A bare
    start_playback followed by a targeted one either 404s or starts playback
    twice.
    """
    fake = client(playback=None)
    state.active_device_id = 'd1'

    assert screens.resume(state) == ('home_screen',)
    assert fake.named('start_playback') == [('start_playback', {'device_id': 'd1'})]


# --- search and track_actions ------------------------------------------------


@pytest.fixture
def fzf_sink(monkeypatch):
    def _install(selection):
        monkeypatch.setattr(
            screens.fzf, 'run_fzf_sink', lambda func, cfg, prompt=None: [selection]
        )

    return _install


def test_search_parses_the_selected_line_into_a_track_ref(state, fzf_sink):
    fzf_sink(
        SEPARATOR.join(
            (
                'Song :: Album :: A, B :: Road Trip',
                'track-1',
                'pl-1',
                'Road Trip',
                '2019-04-03T10:00:00Z',
            )
        )
    )

    choice, track = screens.search(state)

    assert choice == 'track_actions'
    assert track.track_id == 'track-1'
    assert track.playlist_id == 'pl-1'
    assert track.display == 'Song :: Album :: A, B :: Road Trip'
    assert track.playlist_name == 'Road Trip'
    assert track.added_at == '2019-04-03T10:00:00Z'


def test_search_returns_home_when_nothing_was_selected(state, fzf_sink):
    fzf_sink('')

    assert screens.search(state) == ('home_screen',)


def test_track_actions_forwards_the_track_props(state, fzf):
    fzf('Play Track')
    track = track_ref('Song :: Album :: A :: Road Trip')

    assert screens.track_actions(state, track) == ('play_track', track)


def test_track_actions_returns_to_search_on_an_empty_selection(state, fzf):
    fzf('')

    assert screens.track_actions(state, track_ref('Song')) == ('search',)


def test_track_actions_truncates_a_long_prompt(state, fzf):
    seen = fzf('Play Track')

    screens.track_actions(state, track_ref('A' * 40))

    assert seen['prompts'][0] == '[{}...] > '.format('A' * 20)


# --- playback ----------------------------------------------------------------


def test_play_track_starts_the_track_on_the_active_device(state, client):
    fake = client(playback=None)
    state.active_device_id = 'd1'

    track = track_ref('Song')

    assert screens.play_track(state, track) == ('search',)
    assert fake.named('start_playback') == [
        ('start_playback', {'device_id': 'd1', 'uris': ['spotify:track:track-1']})
    ]


def test_play_track_redirects_when_there_is_no_device(state, client):
    fake = client(playback=None)

    track = track_ref('Song')

    assert screens.play_track(state, track) == ('list_devices',)
    assert fake.named('start_playback') == []


def test_play_track_in_playlist_uses_the_playlist_as_context(state, client):
    fake = client(playback=track_playback())

    result = screens.play_track_in_playlist(state, track_ref('Song'))

    assert result == ('search',)
    assert fake.named('start_playback') == [
        (
            'start_playback',
            {
                'device_id': 'device-1',
                'context_uri': 'spotify:playlist:pl-1',
                'offset': {'uri': 'spotify:track:track-1'},
            },
        )
    ]


def test_play_track_in_playlist_is_unaffected_by_the_separator_in_a_name(state, client):
    """
    A name containing ' :: ' used to add fields, which is why the ids were
    addressed by negative index. They have names now, and the name is just
    text inside the display field.
    """
    fake = client(playback=track_playback())

    screens.play_track_in_playlist(
        state,
        track_ref('Intro :: Reprise :: Album :: A :: Road Trip'),
    )

    kwargs = fake.named('start_playback')[0][1]
    assert kwargs['context_uri'] == 'spotify:playlist:pl-1'
    assert kwargs['offset'] == {'uri': 'spotify:track:track-1'}


def test_play_track_in_playlist_redirects_when_there_is_no_device(state, client):
    fake = client(playback=None)

    result = screens.play_track_in_playlist(state, track_ref('Song'))

    assert result == ('list_devices',)
    assert fake.named('start_playback') == []


def test_the_device_redirect_round_trips_back_to_the_original_screen(state, client):
    """
    The whole point of recording the pending screen: picking a device has to
    resume what the user was actually trying to do.
    """
    props = track_ref('Song :: Album :: A :: Road Trip')
    client(playback=None)

    assert screens.play_track(state, props) == ('list_devices',)

    fake = client()
    assert screens.device_actions(state, 'd1') == ('play_track', props)
    assert fake.named('transfer_playback') == [('transfer_playback', 'd1')]
    # The redirect state is consumed, so a later visit goes home instead.
    assert state.pending_screen is None
    assert screens.device_actions(state, 'd1') == ('home_screen',)


def test_the_device_redirect_round_trips_resume(state, client):
    client(playback=None)

    assert screens.resume(state) == ('list_devices',)

    client()
    assert screens.device_actions(state, 'd1') == ('resume',)


def device_gone():
    return SpotifyException(404, -1, 'Device not found')


def test_a_persisted_device_that_no_longer_exists_is_forgotten(state, client):
    """
    Once the device id comes off disk it can be a phone that has been off for a
    week. The user should get the device picker they would have got with no
    device chosen at all, not a traceback out of cli.main.
    """
    props = track_ref('Song')
    client(playback=None, start_error=device_gone())
    state.set_active_device('d1')

    assert screens.play_track(state, props) == ('list_devices',)
    assert state.active_device_id is None
    # Forgotten on disk too, or the next session retries the dead device.
    assert AppState.from_config(state.config).active_device_id is None
    # And the redirect still knows what the user was trying to do.
    assert state.pending_screen == ('play_track', (props,))


def test_resume_forgets_a_persisted_device_that_no_longer_exists(state, client):
    client(playback=None, start_error=device_gone())
    state.set_active_device('d1')

    assert screens.resume(state) == ('list_devices',)
    assert state.active_device_id is None
    assert state.pending_screen == ('resume', ())


# --- update_cache ------------------------------------------------------------


def test_update_cache_screen_delegates_and_returns_home(state, monkeypatch):
    calls = []
    monkeypatch.setattr(screens.spotify, 'update_cache', lambda cfg: calls.append(cfg))

    assert screens.update_cache(state) == ('home_screen',)
    assert calls == [state.config]

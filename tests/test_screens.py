import pytest

from spotifz.interface import screens
from spotifz.state import AppState


class FakeClient:
    def __init__(self, playback=None, devices=()):
        self._playback = playback
        self._devices = list(devices)
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

    def _install(playback=None, devices=()):
        fake = FakeClient(playback, devices)
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


def test_search_splits_the_selected_line(state, fzf_sink):
    fzf_sink('Song :: Album :: A, B :: Road Trip :: pl-1 :: track-1')

    choice, props = screens.search(state)

    assert choice == 'track_actions'
    assert props == ['Song', 'Album', 'A, B', 'Road Trip', 'pl-1', 'track-1']


def test_search_returns_home_when_nothing_was_selected(state, fzf_sink):
    fzf_sink('')

    assert screens.search(state) == ('home_screen',)


def test_track_actions_forwards_the_track_props(state, fzf):
    fzf('Play Track')
    props = ['Song', 'Album', 'A', 'Road Trip', 'pl-1', 'track-1']

    assert screens.track_actions(state, props) == ('play_track', props)


def test_track_actions_returns_to_search_on_an_empty_selection(state, fzf):
    fzf('')

    assert screens.track_actions(state, ['Song']) == ('search',)


def test_track_actions_truncates_a_long_prompt(state, fzf):
    seen = fzf('Play Track')

    screens.track_actions(state, ['A' * 40])

    assert seen['prompts'][0] == '[{}...] > '.format('A' * 20)


# --- playback ----------------------------------------------------------------


def test_play_track_starts_the_track_on_the_active_device(state, client):
    fake = client(playback=None)
    state.active_device_id = 'd1'

    assert screens.play_track(state, ['Song', 'pl-1', 'track-1']) == ('search',)
    assert fake.named('start_playback') == [
        ('start_playback', {'device_id': 'd1', 'uris': ['spotify:track:track-1']})
    ]


def test_play_track_redirects_when_there_is_no_device(state, client):
    fake = client(playback=None)

    assert screens.play_track(state, ['Song', 'pl-1', 'track-1']) == ('list_devices',)
    assert fake.named('start_playback') == []


def test_play_track_in_playlist_uses_the_playlist_as_context(state, client):
    fake = client(playback=track_playback())

    result = screens.play_track_in_playlist(state, ['Song', 'pl-1', 'track-1'])

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


def test_play_track_in_playlist_reads_the_last_two_fields(state, client):
    """
    A name containing the ' :: ' separator adds fields at the front, so the id
    and playlist id are addressed from the end.
    """
    fake = client(playback=track_playback())

    screens.play_track_in_playlist(
        state, ['Intro', 'Reprise', 'Album', 'A', 'Road Trip', 'pl-1', 'track-1']
    )

    kwargs = fake.named('start_playback')[0][1]
    assert kwargs['context_uri'] == 'spotify:playlist:pl-1'
    assert kwargs['offset'] == {'uri': 'spotify:track:track-1'}


def test_play_track_in_playlist_redirects_when_there_is_no_device(state, client):
    fake = client(playback=None)

    result = screens.play_track_in_playlist(state, ['Song', 'pl-1', 'track-1'])

    assert result == ('list_devices',)
    assert fake.named('start_playback') == []


def test_the_device_redirect_round_trips_back_to_the_original_screen(state, client):
    """
    The whole point of recording the pending screen: picking a device has to
    resume what the user was actually trying to do.
    """
    props = ['Song', 'Album', 'A', 'Road Trip', 'pl-1', 'track-1']
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


# --- update_cache ------------------------------------------------------------


def test_update_cache_screen_delegates_and_returns_home(state, monkeypatch):
    calls = []
    monkeypatch.setattr(screens.spotify, 'update_cache', lambda cfg: calls.append(cfg))

    assert screens.update_cache(state) == ('home_screen',)
    assert calls == [state.config]

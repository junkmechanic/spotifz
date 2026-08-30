import json
import os
import shutil

from spotifz.state import PERSISTED_FIELDS, AppState, update_data_paths


def raw_config(cache_path):
    """A config as it comes out of the JSON file, before normalisation."""
    return {
        'spotify_client': {
            'client_id': 'client-id',
            'client_secret': 'client-secret',
            'redirect_uri': 'http://127.0.0.1:8080/',
        },
        'cache_path': cache_path,
        'user': 'tester',
    }


def test_from_config_leaves_the_callers_dict_alone(tmp_path):
    """
    The core claim of the item: loading state must not turn the user's config
    into a scratchpad.
    """
    cfg = raw_config(str(tmp_path / 'cache'))
    before = json.dumps(cfg, sort_keys=True)

    AppState.from_config(cfg)

    assert json.dumps(cfg, sort_keys=True) == before


def test_from_config_normalises_the_config_on_its_own_copy(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    cfg = raw_config('~/.cache/spotifz')

    state = AppState.from_config(cfg)

    assert state.cache_path == str(tmp_path / '.cache/spotifz')
    base = os.path.join(state.cache_path, 'spotify_data')
    assert state.data_paths['base_path'] == base
    assert state.data_paths['playlist_path'] == os.path.join(base, 'playlists')


def test_the_active_device_survives_into_the_next_session(tmp_path):
    """
    The user-facing payoff: the device chosen this run is still chosen next run.
    """
    cfg = raw_config(str(tmp_path / 'cache'))
    AppState.from_config(cfg).set_active_device('d1')

    assert AppState.from_config(cfg).active_device_id == 'd1'


def test_no_state_file_yet_means_no_active_device(tmp_path):
    state = AppState.from_config(raw_config(str(tmp_path / 'cache')))

    assert state.active_device_id is None


def test_a_corrupt_state_file_is_ignored(tmp_path):
    """
    A run killed mid-write must not stop the app from launching at all.
    """
    cfg = raw_config(str(tmp_path / 'cache'))
    state = AppState.from_config(cfg)
    os.makedirs(state.cache_path, exist_ok=True)
    with open(state.state_path, 'w') as ofile:
        ofile.write('{not json')

    assert AppState.from_config(cfg).active_device_id is None


def test_a_state_file_of_the_wrong_shape_is_ignored(tmp_path):
    cfg = raw_config(str(tmp_path / 'cache'))
    state = AppState.from_config(cfg)
    os.makedirs(state.cache_path, exist_ok=True)
    with open(state.state_path, 'w') as ofile:
        json.dump(['not', 'a', 'dict'], ofile)

    assert AppState.from_config(cfg).active_device_id is None


def test_save_writes_exactly_the_persisted_fields(tmp_path):
    """
    The guard that lets a non-serialisable field (a database connection, an API
    client) be added to AppState without silently breaking save().
    """
    state = AppState.from_config(raw_config(str(tmp_path / 'cache')))
    state.set_active_device('d1')

    with open(state.state_path) as ifile:
        written = json.load(ifile)

    assert sorted(written) == sorted(PERSISTED_FIELDS)


def test_the_pending_screen_is_not_persisted(tmp_path):
    """
    Resuming last week's half-finished navigation on startup would be wrong.
    """
    cfg = raw_config(str(tmp_path / 'cache'))
    state = AppState.from_config(cfg)
    state.pending_screen = ('resume', ())
    state.save()

    assert AppState.from_config(cfg).pending_screen is None


def test_save_leaves_no_temporary_file_behind(tmp_path):
    state = AppState.from_config(raw_config(str(tmp_path / 'cache')))
    state.set_active_device('d1')

    assert os.listdir(state.cache_path) == [os.path.basename(state.state_path)]


def test_the_state_file_survives_a_cache_update(tmp_path):
    """
    `spotifz -U` rmtree's data_paths['base_path'] wholesale. Keeping the state
    file outside that directory is the only reason the device is not forgotten
    on every cache update.
    """
    cfg = raw_config(str(tmp_path / 'cache'))
    state = AppState.from_config(cfg)
    state.set_active_device('d1')
    os.makedirs(state.data_paths['playlist_path'], exist_ok=True)

    shutil.rmtree(state.data_paths['base_path'])

    assert os.path.exists(state.state_path)
    assert AppState.from_config(cfg).active_device_id == 'd1'


def test_taking_the_pending_screen_consumes_it(tmp_path):
    state = AppState.from_config(raw_config(str(tmp_path / 'cache')))
    state.pending_screen = ('play_track', (['Song'],))

    assert state.take_pending_screen() == ('play_track', (['Song'],))
    assert state.take_pending_screen() is None


def test_update_data_paths_expands_the_user_directory(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    cfg = {'cache_path': '~/.cache/spotifz'}

    update_data_paths(cfg)

    assert cfg['cache_path'] == str(tmp_path / '.cache/spotifz')


def test_update_data_paths_nests_everything_under_spotify_data():
    cfg = {'cache_path': '/tmp/spotifz-cache'}

    update_data_paths(cfg)

    base = os.path.join('/tmp/spotifz-cache', 'spotify_data')
    assert cfg['data_paths'] == {
        'base_path': base,
        'playlist_path': os.path.join(base, 'playlists'),
        'track_path': os.path.join(base, 'tracks'),
        'album_path': os.path.join(base, 'albums'),
    }

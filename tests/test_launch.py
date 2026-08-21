import os
import types

import pytest

import spotifz
from spotifz.helpers import update_data_paths
from spotifz.state import AppState


def valid_config():
    return {
        'spotify_client': {
            'client_id': 'client-id',
            'client_secret': 'client-secret',
            'redirect_uri': 'http://127.0.0.1:8080/',
        },
        'cache_path': '/tmp/spotifz-cache',
        'user': 'tester',
    }


@pytest.fixture
def no_fzf_check(monkeypatch):
    monkeypatch.setattr(spotifz, 'ensure_fzf', lambda: None)


def test_validate_config_accepts_a_complete_config():
    spotifz.validate_config(valid_config())


def test_validate_config_rejects_a_missing_top_level_key():
    cfg = valid_config()
    del cfg['user']

    with pytest.raises(spotifz.ConfigError, match='user'):
        spotifz.validate_config(cfg)


def test_validate_config_rejects_a_missing_nested_key():
    cfg = valid_config()
    del cfg['spotify_client']['client_secret']

    with pytest.raises(spotifz.ConfigError, match=r'spotify_client\.client_secret'):
        spotifz.validate_config(cfg)


def test_validate_config_rejects_an_empty_value():
    """
    config.json ships with empty strings, so an unfilled copy has every key
    present and no usable value.
    """
    cfg = valid_config()
    cfg['spotify_client']['client_id'] = ''

    with pytest.raises(spotifz.ConfigError, match=r'spotify_client\.client_id'):
        spotifz.validate_config(cfg)


def test_validate_config_rejects_a_non_dict_where_a_dict_is_expected():
    cfg = valid_config()
    cfg['spotify_client'] = 'not-a-dict'

    with pytest.raises(spotifz.ConfigError, match=r'spotify_client\.client_id'):
        spotifz.validate_config(cfg)


def test_validate_config_reports_every_missing_key_at_once():
    with pytest.raises(spotifz.ConfigError) as excinfo:
        spotifz.validate_config({})

    message = str(excinfo.value)
    for expected in (
        'spotify_client.client_id',
        'spotify_client.client_secret',
        'spotify_client.redirect_uri',
        'cache_path',
        'user',
    ):
        assert expected in message


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


def test_launch_walks_screens_until_none(config, monkeypatch, no_fzf_check):
    """
    Pins the screen contract: every screen returns (next_screen_name, *args),
    unpacked as `choice, *screen_args = fn(config, *screen_args)`. Any registry
    replacing the getattr dispatch has to preserve this shape.
    """
    seen = []

    def home_screen(cfg):
        seen.append(('home_screen',))
        return ('track_actions', ['Song', 'pl-1', 'track-1'])

    def track_actions(cfg, track_props):
        seen.append(('track_actions', track_props))
        return 'play_track', track_props

    def play_track(cfg, track_props):
        seen.append(('play_track', track_props))
        return (None,)

    monkeypatch.setattr(
        spotifz,
        'screens',
        types.SimpleNamespace(
            home_screen=home_screen,
            track_actions=track_actions,
            play_track=play_track,
        ),
    )

    spotifz.launch(config)

    assert seen == [
        ('home_screen',),
        ('track_actions', ['Song', 'pl-1', 'track-1']),
        ('play_track', ['Song', 'pl-1', 'track-1']),
    ]


def test_launch_stops_when_the_home_screen_returns_none(
    config, monkeypatch, no_fzf_check
):
    calls = []
    monkeypatch.setattr(
        spotifz,
        'screens',
        types.SimpleNamespace(home_screen=lambda s: calls.append(s) or (None,)),
    )

    spotifz.launch(config)

    assert len(calls) == 1
    assert isinstance(calls[0], AppState)
    assert calls[0].config == config


def test_launch_forwards_several_screen_args(config, monkeypatch, no_fzf_check):
    seen = []

    def home_screen(cfg):
        return ('device_actions', 'device-1', 'extra')

    def device_actions(cfg, device_id, extra):
        seen.append((device_id, extra))
        return (None,)

    monkeypatch.setattr(
        spotifz,
        'screens',
        types.SimpleNamespace(home_screen=home_screen, device_actions=device_actions),
    )

    spotifz.launch(config)

    assert seen == [('device-1', 'extra')]


def test_launch_validates_before_checking_for_fzf(monkeypatch):
    """
    A bad config should be reported as a config problem, not as a missing fzf.
    """
    checked = []
    monkeypatch.setattr(spotifz, 'ensure_fzf', lambda: checked.append(True))

    with pytest.raises(spotifz.ConfigError):
        spotifz.launch({})

    assert checked == []


def test_launch_leaves_the_callers_config_alone(monkeypatch, no_fzf_check):
    """
    The derived paths still get populated -- on the state, not by reaching back
    into the dict the caller loaded from JSON.
    """
    cfg = valid_config()
    seen = []
    monkeypatch.setattr(
        spotifz,
        'screens',
        types.SimpleNamespace(home_screen=lambda s: seen.append(s) or (None,)),
    )

    spotifz.launch(cfg)

    assert cfg == valid_config()
    base = os.path.join('/tmp/spotifz-cache', 'spotify_data')
    assert seen[0].data_paths['base_path'] == base


def test_update_cache_prepares_the_config_first(monkeypatch):
    cfg = valid_config()
    seen = []
    monkeypatch.setattr(
        spotifz.spotify, 'update_cache', lambda c: seen.append(c.get('data_paths'))
    )

    spotifz.update_cache(cfg)

    assert seen and seen[0] is not None


def test_update_cache_rejects_a_bad_config(monkeypatch):
    called = []
    monkeypatch.setattr(spotifz.spotify, 'update_cache', lambda c: called.append(c))

    with pytest.raises(spotifz.ConfigError):
        spotifz.update_cache({})

    assert called == []

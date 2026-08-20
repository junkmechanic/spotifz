import json
import os
import sys

import pytest

import spotifz
from spotifz import cli
from spotifz.helpers import FzfNotFound
from spotifz.spotify.client import SpotifyAuthFailed

VALID_CONFIG = {
    'spotify_client': {
        'client_id': 'client-id',
        'client_secret': 'client-secret',
        'redirect_uri': 'http://127.0.0.1:8080/',
    },
    'cache_path': '~/.cache/spotifz',
    'user': 'tester',
}


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / 'spotifz.json'
    path.write_text(json.dumps(VALID_CONFIG))
    return path


@pytest.fixture
def recorder(monkeypatch):
    """Replaces the two entry points main can dispatch to."""
    calls = {'launch': [], 'update_cache': []}
    monkeypatch.setattr(spotifz, 'launch', lambda cfg: calls['launch'].append(cfg))
    monkeypatch.setattr(
        spotifz, 'update_cache', lambda cfg: calls['update_cache'].append(cfg)
    )
    return calls


def run_main(monkeypatch, *argv):
    monkeypatch.setattr(sys, 'argv', ['spotifz', *argv])
    return cli.main()


def test_load_config_reads_the_file(config_file):
    assert cli.load_config(str(config_file)) == VALID_CONFIG


def test_load_config_expands_the_user_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    os.makedirs(tmp_path / '.config')
    (tmp_path / '.config' / 'spotifz.json').write_text(json.dumps(VALID_CONFIG))

    assert cli.load_config('~/.config/spotifz.json') == VALID_CONFIG


def test_load_config_raises_config_error_when_absent(tmp_path):
    missing = str(tmp_path / 'nope.json')

    with pytest.raises(spotifz.ConfigError) as excinfo:
        cli.load_config(missing)

    # The path matters -- the usual cause is looking in the wrong place.
    assert missing in str(excinfo.value)


def test_load_config_raises_config_error_on_invalid_json(tmp_path):
    path = tmp_path / 'spotifz.json'
    path.write_text('{not json')

    with pytest.raises(spotifz.ConfigError) as excinfo:
        cli.load_config(str(path))

    assert 'not valid JSON' in str(excinfo.value)


def test_main_launches_the_menu(monkeypatch, config_file, recorder):
    assert run_main(monkeypatch, '--config-path', str(config_file)) == 0
    assert recorder['launch'] == [VALID_CONFIG]
    assert recorder['update_cache'] == []


def test_main_updates_the_cache_and_skips_the_menu(monkeypatch, config_file, recorder):
    exit_code = run_main(monkeypatch, '--config-path', str(config_file), '-U')

    assert exit_code == 0
    assert recorder['update_cache'] == [VALID_CONFIG]
    assert recorder['launch'] == []


def test_main_defaults_the_config_path(monkeypatch, tmp_path, recorder):
    monkeypatch.setenv('HOME', str(tmp_path))
    os.makedirs(tmp_path / '.config')
    (tmp_path / '.config' / 'spotifz.json').write_text(json.dumps(VALID_CONFIG))

    assert run_main(monkeypatch) == 0
    assert recorder['launch'] == [VALID_CONFIG]


def test_main_returns_one_on_a_config_error(monkeypatch, tmp_path, recorder, capsys):
    exit_code = run_main(monkeypatch, '--config-path', str(tmp_path / 'nope.json'))

    assert exit_code == 1
    assert 'No config file at' in capsys.readouterr().err
    assert recorder['launch'] == []


@pytest.mark.parametrize(
    'error',
    [
        FzfNotFound('fzf was not found on your PATH.'),
        SpotifyAuthFailed('Could not authenticate with Spotify.'),
        spotifz.ConfigError('Config is missing a value for: user'),
    ],
)
def test_main_returns_one_on_an_expected_failure(
    monkeypatch, config_file, recorder, capsys, error
):
    def raising(_):
        raise error

    monkeypatch.setattr(spotifz, 'launch', raising)

    exit_code = run_main(monkeypatch, '--config-path', str(config_file))

    assert exit_code == 1
    assert str(error) in capsys.readouterr().err


def test_main_returns_130_on_a_keyboard_interrupt(monkeypatch, config_file, recorder):
    def interrupted(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(spotifz, 'launch', interrupted)

    assert run_main(monkeypatch, '--config-path', str(config_file)) == 130


def test_main_does_not_swallow_an_unexpected_error(monkeypatch, config_file, recorder):
    def raising(_):
        raise ValueError('something genuinely unexpected')

    monkeypatch.setattr(spotifz, 'launch', raising)

    with pytest.raises(ValueError):
        run_main(monkeypatch, '--config-path', str(config_file))

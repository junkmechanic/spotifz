import os

import pytest

from spotifz.state import AppState, update_data_paths


@pytest.fixture
def config(tmp_path):
    """
    A config that has already been through update_data_paths, which is what
    every code path below prepare() can assume.
    """
    cfg = {
        'spotify_client': {
            'client_id': 'client-id',
            'client_secret': 'client-secret',
            'redirect_uri': 'http://127.0.0.1:8080/',
        },
        'cache_path': str(tmp_path / 'cache'),
        'user': 'tester',
    }
    update_data_paths(cfg)
    os.makedirs(cfg['cache_path'], exist_ok=True)
    return cfg


@pytest.fixture
def state(config):
    """
    The runtime state built from that config. from_config is idempotent on an
    already-normalised config: expanding an absolute path and recomputing
    data_paths are both no-ops, so both fixtures can be used together.
    """
    return AppState.from_config(config)


@pytest.fixture
def playlist_dir(config):
    path = config['data_paths']['playlist_path']
    os.makedirs(path, exist_ok=True)
    return path


@pytest.fixture
def make_track():
    def _make_track(
        name='Song',
        track_id='track-1',
        artists=('Artist',),
        album='Album',
        added_at=None,
    ):
        """
        A track as Spotify returns it. added_at is off by default because the
        API carries it on the playlist *item*, not on the track -- pass it to
        build a track as it is cached inside a playlist file.
        """
        artist_list = [{'name': artist} for artist in artists]
        track = {
            'id': track_id,
            'name': name,
            'track_number': 1,
            'duration_ms': 215000,
            'uri': 'spotify:track:{}'.format(track_id),
            'artists': artist_list,
            'album': {
                'id': 'album-1',
                'name': album,
                'uri': 'spotify:album:album-1',
                'artists': artist_list,
                'release_date': '1975-11-21',
                'total_tracks': 12,
            },
        }
        if added_at is not None:
            track['added_at'] = added_at
        return track

    return _make_track

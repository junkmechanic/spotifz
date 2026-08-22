import json
import os

from spotifz.spotify import storage
from spotifz.spotify.storage import (
    backup_data,
    cache_data,
    extract_fields,
    iter_spotify_reponse,
    prune_backups,
    update_cache,
)


def pages(*item_lists):
    """Turns lists of items into a chain of response pages."""
    return [{'items': list(items)} for items in item_lists]


class FakeSpotify:
    def __init__(self, playlist_pages, item_pages):
        self._playlist_pages = playlist_pages
        self._item_pages = item_pages
        self.calls = []

    def current_user_playlists(self):
        self.calls.append(('current_user_playlists', None, {}))
        return self._playlist_pages[0]

    def playlist_items(self, playlist_id, **kwargs):
        self.calls.append(('playlist_items', playlist_id, kwargs))
        return self._item_pages[playlist_id][0]

    def next(self, response):
        for chain in [self._playlist_pages] + list(self._item_pages.values()):
            for index, page in enumerate(chain):
                if page is response:
                    return chain[index + 1] if index + 1 < len(chain) else None
        return None


def playlist_response(playlist_id, name):
    return {
        'id': playlist_id,
        'name': name,
        'href': 'https://api.spotify.com/playlists/{}'.format(playlist_id),
        'uri': 'spotify:playlist:{}'.format(playlist_id),
        'extra': 'dropped by extract_fields',
    }


def read(path):
    with open(path) as ifile:
        return json.load(ifile)


def test_iter_spotify_reponse_follows_pagination():
    client = FakeSpotify(pages(['a', 'b'], ['c']), {})

    assert list(iter_spotify_reponse(client, 'current_user_playlists')) == [
        'a',
        'b',
        'c',
    ]


def test_extract_fields_keeps_only_the_requested_keys():
    assert extract_fields({'a': 1, 'b': 2, 'c': 3}, ['a', 'c']) == {'a': 1, 'c': 3}


def test_extract_fields_tolerates_a_missing_key():
    assert extract_fields({'a': 1}, ['a', 'nope']) == {'a': 1}


def test_cache_data_requests_only_tracks(config, make_track):
    """
    Without additional_types=('track',) Spotify also returns podcast episodes,
    which carry no album/artists and would blow up extract_fields below.
    """
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {'pl-1': pages([{'track': make_track()}])},
    )

    cache_data(client, config)

    item_calls = [call for call in client.calls if call[0] == 'playlist_items']
    assert item_calls[0][2]['additional_types'] == ('track',)


def test_cache_data_creates_the_data_directories(config, make_track):
    client = FakeSpotify(pages([]), {})

    cache_data(client, config)

    for dir_path in config['data_paths'].values():
        assert os.path.isdir(dir_path)


def test_cache_data_writes_a_file_per_track_album_and_playlist(config, make_track):
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {'pl-1': pages([{'track': make_track(track_id='track-1')}])},
    )

    cache_data(client, config)

    track = read(os.path.join(config['data_paths']['track_path'], 'track-1'))
    album = read(os.path.join(config['data_paths']['album_path'], 'album-1'))
    playlist = read(os.path.join(config['data_paths']['playlist_path'], 'pl-1'))

    assert track['name'] == 'Song'
    assert album['name'] == 'Album'
    assert playlist['name'] == 'First'
    assert [t['id'] for t in playlist['tracks']] == ['track-1']
    # extract_fields drops everything not asked for.
    assert 'extra' not in playlist


def test_cache_data_keeps_the_fields_the_preview_needs(config, make_track):
    """
    duration_ms on the track, release_date and total_tracks on the album: the
    preview pane renders all three, and the album ones have to survive on the
    album nested inside the track file, which is the only file it opens.
    """
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {'pl-1': pages([{'track': make_track(track_id='track-1')}])},
    )

    cache_data(client, config)

    track = read(os.path.join(config['data_paths']['track_path'], 'track-1'))
    assert track['duration_ms'] == 215000
    assert track['album']['release_date'] == '1975-11-21'
    assert track['album']['total_tracks'] == 12

    album = read(os.path.join(config['data_paths']['album_path'], 'album-1'))
    assert album['release_date'] == '1975-11-21'
    assert album['total_tracks'] == 12


def test_cache_data_tolerates_a_track_without_those_fields(config, make_track):
    """
    Spotify does not promise them on every response, and extract_fields only
    copies what it finds, so an absent field must leave the entry writable
    rather than raising.
    """
    sparse = make_track(track_id='track-1')
    del sparse['duration_ms']
    del sparse['album']['release_date']
    del sparse['album']['total_tracks']
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {'pl-1': pages([{'track': sparse}])},
    )

    cache_data(client, config)

    track = read(os.path.join(config['data_paths']['track_path'], 'track-1'))
    assert 'duration_ms' not in track
    assert 'release_date' not in track['album']
    assert 'total_tracks' not in track['album']
    assert track['name'] == 'Song'


def test_cache_data_keeps_added_at_on_the_playlist_entry_only(config, make_track):
    """
    added_at describes the track-playlist pair, so it belongs to the playlist's
    copy of the track. The per-track file is keyed by track id alone: a track
    in three playlists has three added_at values and no way to hold them.
    """
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {
            'pl-1': pages(
                [
                    {
                        'track': make_track(track_id='track-1'),
                        'added_at': '2019-04-03T10:00:00Z',
                    }
                ]
            )
        },
    )

    cache_data(client, config)

    playlist = read(os.path.join(config['data_paths']['playlist_path'], 'pl-1'))
    assert playlist['tracks'][0]['added_at'] == '2019-04-03T10:00:00Z'

    track = read(os.path.join(config['data_paths']['track_path'], 'track-1'))
    assert 'added_at' not in track


def test_cache_data_records_no_added_at_when_spotify_sends_none(config, make_track):
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {'pl-1': pages([{'track': make_track(track_id='track-1')}])},
    )

    cache_data(client, config)

    playlist = read(os.path.join(config['data_paths']['playlist_path'], 'pl-1'))
    assert playlist['tracks'][0]['added_at'] is None


def test_cache_data_paginates_through_a_playlists_tracks(config, make_track):
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {
            'pl-1': pages(
                [{'track': make_track(track_id='track-1')}],
                [{'track': make_track(track_id='track-2')}],
            )
        },
    )

    cache_data(client, config)

    playlist = read(os.path.join(config['data_paths']['playlist_path'], 'pl-1'))
    assert [t['id'] for t in playlist['tracks']] == ['track-1', 'track-2']


def test_cache_data_records_every_playlist_a_track_appears_in(config, make_track):
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First'), playlist_response('pl-2', 'Second')]),
        {
            'pl-1': pages([{'track': make_track(track_id='track-1')}]),
            'pl-2': pages([{'track': make_track(track_id='track-1')}]),
        },
    )

    cache_data(client, config)

    track = read(os.path.join(config['data_paths']['track_path'], 'track-1'))
    assert sorted(track['playlists']) == ['pl-1', 'pl-2']


def test_cache_data_skips_a_track_whose_id_is_missing(config, make_track, capsys):
    """
    A track pulled from the Spotify catalogue can arrive with a null id, which
    makes os.path.join raise TypeError rather than KeyError.
    """
    orphan = make_track(track_id='track-1')
    orphan['id'] = None
    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {'pl-1': pages([{'track': orphan}])},
    )

    cache_data(client, config)

    assert os.listdir(config['data_paths']['track_path']) == []
    assert 'First' in capsys.readouterr().out
    # The playlist itself is still written, album included.
    assert os.path.exists(os.path.join(config['data_paths']['playlist_path'], 'pl-1'))


def test_prune_backups_keeps_only_the_newest(tmp_path):
    backup_dir = tmp_path / 'backup'
    backup_dir.mkdir()
    names = [
        'spotify_data_20260101T000000.tar.gz',
        'spotify_data_20260102T000000.tar.gz',
        'spotify_data_20260103T000000.tar.gz',
        'spotify_data_20260104T000000.tar.gz',
    ]
    for name in names:
        (backup_dir / name).write_text('archive')

    removed = prune_backups(str(backup_dir), keep=2)

    assert removed == names[:2]
    assert sorted(os.listdir(str(backup_dir))) == names[2:]


def test_prune_backups_ignores_unrelated_files(tmp_path):
    backup_dir = tmp_path / 'backup'
    backup_dir.mkdir()
    (backup_dir / 'spotify_data_20260101T000000.tar.gz').write_text('archive')
    (backup_dir / 'notes.txt').write_text('keep me')

    prune_backups(str(backup_dir), keep=0)

    assert os.listdir(str(backup_dir)) == ['notes.txt']


def test_prune_backups_returns_nothing_when_the_directory_is_absent(tmp_path):
    assert prune_backups(str(tmp_path / 'missing')) == []


def test_backup_data_returns_none_without_existing_data(config):
    assert backup_data(config) is None


def test_backup_data_archives_the_existing_cache(config, monkeypatch):
    os.makedirs(config['data_paths']['track_path'])
    with open(os.path.join(config['data_paths']['track_path'], 'track-1'), 'w') as ofile:
        ofile.write('{}')

    archive_path = backup_data(config)

    assert archive_path.endswith('.tar.gz')
    assert os.path.exists(archive_path)


def test_update_cache_wipes_the_directory_before_rebuilding(
    config, make_track, monkeypatch
):
    """
    Stale entries -- a track removed from a playlist upstream -- would
    otherwise survive forever, since cache_data only ever writes.
    """
    os.makedirs(config['data_paths']['track_path'])
    stale = os.path.join(config['data_paths']['track_path'], 'gone-from-spotify')
    with open(stale, 'w') as ofile:
        ofile.write('{}')

    client = FakeSpotify(
        pages([playlist_response('pl-1', 'First')]),
        {'pl-1': pages([{'track': make_track(track_id='track-1')}])},
    )
    monkeypatch.setattr(storage, 'get_spotify_client', lambda cfg: client)

    update_cache(config, backup=False)

    assert not os.path.exists(stale)
    assert os.path.exists(os.path.join(config['data_paths']['track_path'], 'track-1'))


def test_update_cache_backs_up_by_default(config, make_track, monkeypatch):
    calls = []
    monkeypatch.setattr(storage, 'backup_data', lambda cfg: calls.append(cfg) or None)
    client = FakeSpotify(pages([]), {})
    monkeypatch.setattr(storage, 'get_spotify_client', lambda cfg: client)

    update_cache(config)

    assert calls == [config]

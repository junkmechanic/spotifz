import pytest

from builders import history_item, playlist_context
from spotifz.spotify import history


def test_context_playlist_id_reads_a_playlist():
    assert history.context_playlist_id(playlist_context('pl-1')) == 'pl-1'


@pytest.mark.parametrize(
    'context',
    [
        None,
        {},
        {'type': 'album', 'uri': 'spotify:album:al-1'},
        {'type': 'artist', 'uri': 'spotify:artist:ar-1'},
        {'type': 'collection', 'uri': 'spotify:user:tester:collection'},
        {'type': 'playlist', 'uri': 'spotify:playlist:'},
        {'type': 'playlist'},
    ],
)
def test_context_playlist_id_reads_nothing_else(context):
    assert history.context_playlist_id(context) is None


def test_history_entries_says_nothing_without_a_response():
    """No history at all comes back as a 204, which spotipy returns as None."""
    assert history.history_entries(None) == []
    assert history.history_entries({}) == []
    assert history.history_entries({'items': None}) == []


def test_history_entries_reads_a_track():
    entry = history.history_entries({'items': [history_item()]})[0]

    assert entry.name == 'Song'
    assert entry.track['album']['name'] == 'Album'
    assert entry.track_id == 'track-1'
    assert entry.played_at == '2026-08-30T10:00:00.123Z'
    assert entry.context_uri is None
    assert entry.context_name is None


def test_history_entries_names_a_cached_playlist():
    response = {'items': [history_item(context=playlist_context('pl-1'))]}

    entry = history.history_entries(response, {'pl-1': 'Road Trip'})[0]

    assert entry.context_name == 'Road Trip'
    assert entry.context_uri == 'spotify:playlist:pl-1'
    assert entry.context_type == 'playlist'


def test_history_entries_leaves_an_uncached_playlist_unnamed():
    """
    Someone else's playlist, or one added since the last Update Cache. The row
    keeps everything the API gave it and just gains no fourth field.
    """
    response = {'items': [history_item(context=playlist_context('pl-9'))]}

    entry = history.history_entries(response, {'pl-1': 'Road Trip'})[0]

    assert entry.context_name is None
    # Still resumable: the action does not need the name, only the uri.
    assert entry.context_uri == 'spotify:playlist:pl-9'
    assert entry.is_resumable


def test_history_entries_names_an_album_context_off_the_track():
    """
    No lookup needed: an album context is the album the track already names.
    """
    context = {'type': 'album', 'uri': 'spotify:album:al-1'}
    response = {'items': [history_item(album='Mezzanine', context=context)]}

    entry = history.history_entries(response)[0]

    assert entry.context_name == 'Mezzanine'
    assert entry.is_resumable


def test_history_entries_skips_an_entry_without_a_track():
    response = {'items': [history_item(), None, {'track': None}, history_item('Other')]}

    assert [entry.name for entry in history.history_entries(response)] == [
        'Song',
        'Other',
    ]


def test_an_entry_is_only_resumable_in_a_playlist_or_an_album():
    """
    Spotify accepts the offset that starts a context at the chosen track only
    for those two; anywhere else it would start somewhere the user did not pick.
    """
    resumable = {
        'playlist': 'spotify:playlist:pl-1',
        'album': 'spotify:album:al-1',
    }
    for context_type, uri in resumable.items():
        context = {'type': context_type, 'uri': uri}
        assert history.history_entries({'items': [history_item(context=context)]})[
            0
        ].is_resumable, context_type

    not_resumable = {
        'artist': 'spotify:artist:ar-1',
        'collection': 'spotify:user:tester:collection',
    }
    for context_type, uri in not_resumable.items():
        context = {'type': context_type, 'uri': uri}
        assert not history.history_entries({'items': [history_item(context=context)]})[
            0
        ].is_resumable, context_type

    assert not history.history_entries({'items': [history_item()]})[0].is_resumable


def test_history_playlist_ids_lists_what_the_caller_has_to_look_up():
    response = {
        'items': [
            history_item(context=playlist_context('pl-1')),
            history_item(context={'type': 'album', 'uri': 'spotify:album:al-1'}),
            history_item(context=None),
            history_item(context=playlist_context('pl-2')),
        ]
    }

    assert history.history_playlist_ids(response) == ['pl-1', 'pl-2']


def test_history_playlist_ids_says_nothing_without_a_response():
    assert history.history_playlist_ids(None) == []

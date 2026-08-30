"""
Builders for Spotify responses that more than one test module needs. Anything
used by a single module stays a local helper in it, as most of these are.
"""


def history_item(
    name='Song',
    track_id='track-1',
    album='Album',
    artists=('A', 'B'),
    context=None,
    played_at='2026-08-30T10:00:00.123Z',
):
    """One entry as `me/player/recently-played` returns it."""
    return {
        'track': {
            'type': 'track',
            'id': track_id,
            'name': name,
            'album': {'name': album},
            'artists': [{'name': artist} for artist in artists],
        },
        'context': context,
        'played_at': played_at,
    }


def playlist_context(playlist_id='pl-1'):
    return {'type': 'playlist', 'uri': 'spotify:playlist:{}'.format(playlist_id)}

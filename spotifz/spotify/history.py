from typing import Any, Dict, NamedTuple, Optional

# Contexts a track can be resumed *inside*. Spotify accepts the `offset` that
# starts a context at a chosen track only for these two, so an artist or a
# Liked Songs context would start somewhere the user did not pick.
RESUMABLE_CONTEXTS = ('playlist', 'album')
PLAYLIST_URI_PREFIX = 'spotify:playlist:'


class HistoryEntry(NamedTuple):
    """
    One play out of `me/player/recently-played`. `track_id` and `name` are
    spelled the way TrackRef spells them, which is what lets play_track and
    add_to_queue take an entry without knowing which list it was picked from.

    It holds the track it was given rather than a rendered row: what a play
    looks like on screen belongs to whatever is doing the rendering, and a
    record that stored the row would only have to be taken apart again to
    recover the fields it was built from.
    """

    track: Dict[str, Any]
    track_id: Optional[str]
    context_uri: Optional[str]
    context_type: Optional[str]
    # What the context is called, where that is known without asking Spotify:
    # a playlist of the user's own is named by the cache, an album by the track
    # itself. An artist or Liked Songs context goes unnamed.
    context_name: Optional[str]
    played_at: str

    @property
    def name(self):
        return self.track.get('name') or ''

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


def history_playlist_ids(response):
    """The playlist ids a response refers to, for the caller's cache read."""
    ids = (
        context_playlist_id((item or {}).get('context'))
        for item in (response or {}).get('items') or []
    )
    return [playlist_id for playlist_id in ids if playlist_id]


def history_entries(response, playlist_names=None):
    """
    Maps the recently-played response onto entries. `playlist_names` is handed
    in rather than read here -- storage.read_playlist_names is what produces it
    -- so this stays a pure function of the response, and the one cache read is
    the caller's.
    """
    playlist_names = playlist_names or {}
    entries = []
    for item in (response or {}).get('items') or []:
        track = (item or {}).get('track')
        if not track:
            continue
        context = item.get('context') or None
        context_type = (context or {}).get('type')
        playlist_id = context_playlist_id(context)
        if playlist_id:
            context_name = playlist_names.get(playlist_id)
        elif context_type == 'album':
            context_name = (track.get('album') or {}).get('name')
        else:
            context_name = None

        entries.append(
            HistoryEntry(
                track=track,
                track_id=track.get('id'),
                context_uri=(context or {}).get('uri'),
                context_type=context_type,
                context_name=context_name or None,
                played_at=item.get('played_at') or '',
            )
        )
    return entries

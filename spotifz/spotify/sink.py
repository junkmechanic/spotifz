import json
import os
from glob import glob
from typing import NamedTuple

# The candidate line fzf reads is
# `<display>\x1f<track_id>\x1f<playlist_id>\x1f<playlist_name>\x1f<added_at>`.
#
# 0x1f (ASCII Unit Separator) is the only field separator, and it cannot occur
# in a track, album or playlist name. ' :: ' is decoration inside the display
# field, free to appear in a name: it used to be the separator, which meant a
# name containing it shifted every field after it and the preview pane read the
# wrong one.
SEPARATOR = '\x1f'
DISPLAY_SEPARATOR = ' :: '

# 1-based, to match fzf's {N} placeholders and --with-nth.
DISPLAY_FIELD = 1
TRACK_ID_FIELD = 2
PLAYLIST_ID_FIELD = 3
# Fields 4 and 5 exist for the preview pane, which is handed values rather than
# a line: it renders the playlist a track was picked from and when it was added
# there. Both belong to the track-playlist pair, so neither can be read from
# the per-track cache file the preview opens.
PLAYLIST_NAME_FIELD = 4
ADDED_AT_FIELD = 5


class TrackRef(NamedTuple):
    display: str
    track_id: str
    playlist_id: str
    playlist_name: str
    added_at: str

    @property
    def name(self):
        # Cosmetic, for the fzf prompt only. A name containing
        # DISPLAY_SEPARATOR truncates the prompt and nothing else.
        return self.display.split(DISPLAY_SEPARATOR)[0]

    @property
    def context_uri(self):
        # What to play this track *within*. A track reached through the search
        # was found inside a playlist, so that is its context; other sources of
        # a track carry a context of their own and name it the same way.
        return 'spotify:playlist:{}'.format(self.playlist_id)


def _clean(value):
    """
    One record per line, SEPARATOR between fields: nothing that could
    impersonate either may survive into a field.
    """
    for char in ('\n', '\r', SEPARATOR):
        value = value.replace(char, ' ')
    return value


def format_track_line(track, playlist):
    display = DISPLAY_SEPARATOR.join(
        _clean(part)
        for part in (
            track['name'],
            track['album']['name'],
            ', '.join(artist['name'] for artist in track['artists']),
            playlist['name'],
        )
    )
    # The playlist name is deliberately carried twice: once as decoration
    # inside the display field, and once whole in field 4. The display field is
    # a presentation string -- _clean'ed and DISPLAY_SEPARATOR-joined -- and
    # re-parsing it to recover a name is exactly the fragility this format
    # removed. Two fields written here together cannot drift.
    return (
        SEPARATOR.join(
            (
                display,
                track['id'],
                playlist['id'],
                _clean(playlist['name']),
                # Absent from any Spotify item that arrives without it.
                _clean(track.get('added_at') or ''),
            )
        )
        + '\n'
    )


def parse_track_line(line):
    display, track_id, playlist_id, playlist_name, added_at = line.split(SEPARATOR)
    return TrackRef(display, track_id, playlist_id, playlist_name, added_at)


def sink_all_tracks(config, fifo_path):
    try:
        with open(fifo_path, 'w') as sink:
            for p_file in glob(os.path.join(config['data_paths']['playlist_path'], '*')):
                with open(p_file) as ifi:
                    playlist = json.load(ifi)
                for track in playlist['tracks']:
                    sink.write(format_track_line(track, playlist))
    except BrokenPipeError:
        # fzf was closed before every track had been written, e.g. the user
        # picked a track or hit Esc. Nothing left to sink.
        pass

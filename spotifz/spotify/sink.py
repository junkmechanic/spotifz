import json
import os
from glob import glob
from typing import NamedTuple

# The candidate line fzf reads is `<display>\x1f<track_id>\x1f<playlist_id>`.
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


class TrackRef(NamedTuple):
    display: str
    track_id: str
    playlist_id: str

    @property
    def name(self):
        # Cosmetic, for the fzf prompt only. A name containing
        # DISPLAY_SEPARATOR truncates the prompt and nothing else.
        return self.display.split(DISPLAY_SEPARATOR)[0]


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
    return SEPARATOR.join((display, track['id'], playlist['id'])) + '\n'


def parse_track_line(line):
    display, track_id, playlist_id = line.split(SEPARATOR)
    return TrackRef(display, track_id, playlist_id)


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

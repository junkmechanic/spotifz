import json
import os
import threading

from spotifz.spotify.sink import (
    ADDED_AT_FIELD,
    PLAYLIST_NAME_FIELD,
    SEPARATOR,
    TRACK_ID_FIELD,
    format_track_line,
    parse_track_line,
    sink_all_tracks,
)


def write_playlist(playlist_dir, playlist_id, name, tracks):
    with open(os.path.join(playlist_dir, playlist_id), 'w') as ofile:
        json.dump({'id': playlist_id, 'name': name, 'tracks': tracks}, ofile)


def drain(config, fifo_path):
    """
    sink_all_tracks blocks on opening the FIFO for writing until a reader
    arrives, so every test needs one.
    """
    lines = []

    def _read():
        with open(fifo_path) as sink:
            lines.extend(sink.read().splitlines())

    reader = threading.Thread(target=_read)
    reader.start()
    sink_all_tracks(config, fifo_path)
    reader.join()
    return lines


def make_fifo(config):
    fifo_path = os.path.join(config['cache_path'], 'fifo')
    os.mkfifo(fifo_path)
    return fifo_path


def test_sinks_a_display_two_ids_and_the_pair_data_per_track(
    config, playlist_dir, make_track
):
    write_playlist(
        playlist_dir,
        'pl-1',
        'Road Trip',
        [
            make_track(
                name='Song One',
                track_id='track-1',
                artists=('A', 'B'),
                added_at='2019-04-03T10:00:00Z',
            )
        ],
    )

    lines = drain(config, make_fifo(config))

    assert lines == [
        'Song One :: Album :: A, B :: Road Trip'
        '\x1ftrack-1\x1fpl-1\x1fRoad Trip\x1f2019-04-03T10:00:00Z'
    ]
    # The preview pane's `{N}` placeholders depend on the field positions.
    fields = lines[0].split(SEPARATOR)
    assert fields[TRACK_ID_FIELD - 1] == 'track-1'
    assert fields[PLAYLIST_NAME_FIELD - 1] == 'Road Trip'
    assert fields[ADDED_AT_FIELD - 1] == '2019-04-03T10:00:00Z'


def test_sinks_an_empty_added_at_for_a_track_cached_without_one(
    config, playlist_dir, make_track
):
    """
    Every entry cached before added_at was kept lacks it, and the line must
    still hold five fields -- an empty one the preview omits, not a short line
    that shifts every placeholder after it.
    """
    write_playlist(playlist_dir, 'pl-1', 'Road Trip', [make_track(track_id='track-1')])

    lines = drain(config, make_fifo(config))
    fields = lines[0].split(SEPARATOR)

    assert len(fields) == 5
    assert fields[ADDED_AT_FIELD - 1] == ''
    assert fields[TRACK_ID_FIELD - 1] == 'track-1'


def test_sinks_every_track_of_every_playlist(config, playlist_dir, make_track):
    write_playlist(playlist_dir, 'pl-1', 'First', [make_track(track_id='a')])
    write_playlist(
        playlist_dir,
        'pl-2',
        'Second',
        [make_track(track_id='b'), make_track(track_id='c')],
    )

    lines = drain(config, make_fifo(config))

    assert sorted(parse_track_line(line).track_id for line in lines) == ['a', 'b', 'c']


def test_sinks_playlists_regardless_of_characters_in_the_id(
    config, playlist_dir, make_track
):
    """
    The playlist directory is read wholesale -- every file in it is a playlist,
    and Spotify ids are opaque strings that can end in any character.

    If a future change puts a non-playlist file in this directory (a manifest,
    an index, a database), do not filter by filename pattern: the ids below are
    the ones a plausible pattern would exclude by accident, and losing a
    playlist here is silent. Tracks simply stop appearing in search.
    """
    for playlist_id in ('endsinj', 'endsins', 'endsino', 'endsinn', 'plainid'):
        write_playlist(
            playlist_dir, playlist_id, playlist_id, [make_track(track_id=playlist_id)]
        )

    lines = drain(config, make_fifo(config))

    assert sorted(parse_track_line(line).playlist_id for line in lines) == [
        'endsinj',
        'endsinn',
        'endsino',
        'endsins',
        'plainid',
    ]


def test_a_broken_pipe_is_swallowed(config, playlist_dir, make_track):
    """
    fzf closing early -- the user picked something or hit Esc -- must not
    surface as an exception.
    """
    write_playlist(
        playlist_dir,
        'pl-1',
        'Long',
        [make_track(track_id='track-{}'.format(i)) for i in range(5000)],
    )
    fifo_path = make_fifo(config)

    def _read_one_then_close():
        with open(fifo_path) as sink:
            sink.readline()

    reader = threading.Thread(target=_read_one_then_close)
    reader.start()
    try:
        # No exception, despite the reader going away mid-write.
        sink_all_tracks(config, fifo_path)
    finally:
        reader.join()


def test_names_containing_the_display_separator_do_not_shift_the_fields(
    config, playlist_dir, make_track
):
    """
    ' :: ' is decoration inside the display field now, so a name may contain
    it. This test used to document the opposite: it asserted seven fields and
    an id pushed out of position six, which is what broke the preview pane.
    """
    write_playlist(
        playlist_dir,
        'pl-1',
        'Mix',
        [make_track(name='Intro :: Reprise', track_id='track-1')],
    )

    lines = drain(config, make_fifo(config))
    fields = lines[0].split(SEPARATOR)

    assert len(fields) == 5
    # The positive index works now -- that is the whole point.
    assert fields[TRACK_ID_FIELD - 1] == 'track-1'
    # And the name survives intact in the display.
    assert fields[0].startswith('Intro :: Reprise')


def test_format_track_line_removes_a_separator_from_a_name(make_track):
    """
    SEPARATOR cannot occur in a real Spotify name, but the line protocol should
    not depend on that being true.
    """
    track = make_track(name='Side A\x1fSide B', track_id='track-1')

    line = format_track_line(track, {'id': 'pl-1', 'name': 'Mix'})

    assert len(line.rstrip('\n').split(SEPARATOR)) == 5
    assert parse_track_line(line.rstrip('\n')).track_id == 'track-1'


def test_format_track_line_removes_a_separator_from_a_playlist_name(make_track):
    """
    Field 4 is a name straight from the cache, so it needs the same cleaning
    the display field gets -- a separator inside it would shift added_at.
    """
    track = make_track(track_id='track-1', added_at='2019-04-03T10:00:00Z')

    line = format_track_line(track, {'id': 'pl-1', 'name': 'Party\x1fMix'})

    assert len(line.rstrip('\n').split(SEPARATOR)) == 5
    ref = parse_track_line(line.rstrip('\n'))
    assert ref.playlist_name == 'Party Mix'
    assert ref.added_at == '2019-04-03T10:00:00Z'


def test_format_track_line_removes_a_newline_from_a_name(make_track):
    """One record is one line, so a name may not end it early."""
    track = make_track(name='First\nSecond', track_id='track-1')

    line = format_track_line(track, {'id': 'pl-1', 'name': 'Mix'})

    assert line.count('\n') == 1
    assert line.endswith('\n')


def test_parse_track_line_round_trips_what_format_wrote(make_track):
    """
    Pins the writer and the reader to each other. Their drifting apart -- one
    joining on ' :: ', the other splitting on '::' -- is what item 7 was.
    """
    track = make_track(
        name='Song :: One',
        track_id='track-1',
        artists=('A', 'B'),
        added_at='2019-04-03T10:00:00Z',
    )

    ref = parse_track_line(
        format_track_line(track, {'id': 'pl-1', 'name': 'Road Trip'}).rstrip('\n')
    )

    assert ref.track_id == 'track-1'
    assert ref.playlist_id == 'pl-1'
    assert ref.playlist_name == 'Road Trip'
    assert ref.added_at == '2019-04-03T10:00:00Z'
    # The full name survives on the line and in the display...
    assert ref.display.startswith('Song :: One')
    # ...but `name` is prompt decoration and stops at the display separator.
    # Cosmetic, and the only thing ' :: ' in a name still affects.
    assert ref.name == 'Song'

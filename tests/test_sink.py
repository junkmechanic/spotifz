import json
import os
import threading

from spotifz.spotify.sink import sink_all_tracks


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


def test_sinks_a_six_field_line_per_track(config, playlist_dir, make_track):
    write_playlist(
        playlist_dir,
        'pl-1',
        'Road Trip',
        [make_track(name='Song One', track_id='track-1', artists=('A', 'B'))],
    )

    lines = drain(config, make_fifo(config))

    assert lines == ['Song One :: Album :: A, B :: Road Trip :: pl-1 :: track-1']
    # The preview pane's `awk -F " :: " '{print $6}'` depends on the id being
    # the sixth field.
    assert lines[0].split(' :: ')[5] == 'track-1'


def test_sinks_every_track_of_every_playlist(config, playlist_dir, make_track):
    write_playlist(playlist_dir, 'pl-1', 'First', [make_track(track_id='a')])
    write_playlist(
        playlist_dir,
        'pl-2',
        'Second',
        [make_track(track_id='b'), make_track(track_id='c')],
    )

    lines = drain(config, make_fifo(config))

    assert sorted(line.split(' :: ')[5] for line in lines) == ['a', 'b', 'c']


def test_sinks_playlists_whose_ids_end_in_json_characters(
    config, playlist_dir, make_track
):
    """
    The original glob was '*[!json]', which excludes any id ending in one of
    j/s/o/n rather than excluding a '.json' suffix. Reintroducing it drops
    every id below except 'plainid'.
    """
    for playlist_id in ('endsinj', 'endsins', 'endsino', 'endsinn', 'plainid'):
        write_playlist(
            playlist_dir, playlist_id, playlist_id, [make_track(track_id=playlist_id)]
        )

    lines = drain(config, make_fifo(config))

    assert sorted(line.split(' :: ')[4] for line in lines) == [
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


def test_names_containing_the_separator_shift_the_fields(
    config, playlist_dir, make_track
):
    """
    Documents the bug rather than asserting it is fixed: ' :: ' is not
    escaped, so a name containing it produces seven fields and pushes the id
    out of position six. Invert this test when the separator is replaced.
    """
    write_playlist(
        playlist_dir,
        'pl-1',
        'Mix',
        [make_track(name='Intro :: Reprise', track_id='track-1')],
    )

    lines = drain(config, make_fifo(config))
    fields = lines[0].split(' :: ')

    assert len(fields) == 7
    assert fields[5] != 'track-1'
    # The negative index that screens.py relies on still finds it.
    assert fields[-1] == 'track-1'

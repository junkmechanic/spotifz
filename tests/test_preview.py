import datetime
import importlib.util
import json
import os
import subprocess
import sys

import pytest

PREVIEW_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'spotifz',
    'preview.py',
)

# Fixed so the relative dates below are not a moving target. Six years and a
# few months after the added_at every test uses.
NOW = datetime.datetime(2026, 8, 22, 12, 0, tzinfo=datetime.timezone.utc)
ADDED_AT = '2019-04-03T10:00:00Z'


@pytest.fixture(scope='module')
def preview():
    """
    Loaded from its path, the way it is run: importing spotifz.preview would
    pull in the package -- and spotipy behind it -- which is the one thing the
    renderer exists to avoid.
    """
    spec = importlib.util.spec_from_file_location('preview_under_test', PREVIEW_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def track_dir(tmp_path):
    path = tmp_path / 'tracks'
    path.mkdir()
    return str(path)


@pytest.fixture
def write_track(track_dir):
    def _write_track(track):
        with open(os.path.join(track_dir, 'track-1'), 'w') as ofile:
            json.dump(track, ofile)
        return track

    return _write_track


@pytest.fixture
def cache_track(write_track, make_track):
    def _cache_track(**overrides):
        track = make_track(track_id='track-1')
        track.update(overrides)
        return write_track(track)

    return _cache_track


def plain(preview):
    """The identity styles, i.e. what NO_COLOR gives."""
    return preview.styles({'NO_COLOR': '1'})


def pane(preview, track_dir, playlist_name='Road Trip', added_at=ADDED_AT, width=100):
    bold, dim = plain(preview)
    track = preview.load_track(track_dir, 'track-1')
    return preview.render(track, playlist_name, added_at, width, bold, dim, NOW)


def test_renders_the_whole_pane(preview, track_dir, cache_track):
    """
    The golden test. It pins the layout whole -- indentation, the label column,
    the blank line between groups -- so that changing any of it is a visible
    diff in review rather than a surprise in the terminal.
    """
    cache_track()

    assert pane(preview, track_dir) == (
        '  Song\n'
        '  Artist\n'
        '\n'
        '  Album       Album (1975)\n'
        '  Track       1 of 12\n'
        '  Length      3:35\n'
        '\n'
        '  Playlist    Road Trip\n'
        '  Added       3 April 2019 · 7 years ago'
    )


def test_names_the_album_artist_only_when_it_differs(
    preview, track_dir, cache_track, write_track
):
    """The compilation tell: silent on a normal album, present on a soundtrack."""
    track = cache_track()
    track['album']['artists'] = [{'name': 'Various Artists'}]
    write_track(track)

    assert '  Album by    Various Artists\n' in pane(preview, track_dir) + '\n'


def test_collapses_the_album_row_of_a_single(
    preview, track_dir, cache_track, write_track
):
    """
    A single carries the track's own name as its album, so the row says the
    title back to you and 'Track 1 of 1' gives a position with no scale. Both
    go; the year, the only thing the album added, stays. album_type would say
    outright that it is a single, but is not cached -- a one-track album under
    the same name is the same fact.
    """
    track = cache_track(name='Sunset Lover')
    track['album'].update(
        {'name': 'Sunset Lover', 'total_tracks': 1, 'release_date': '2016-03-04'}
    )
    write_track(track)

    rendered = pane(preview, track_dir)

    assert '  Single      2016\n' in rendered + '\n'
    assert 'Album' not in rendered
    assert 'Track' not in rendered


def test_keeps_the_album_row_of_a_one_track_album_named_differently(
    preview, track_dir, cache_track, write_track
):
    """One track, but not the same name: that is an album, oddly sized."""
    track = cache_track(name='Sunset Lover')
    track['album'].update({'name': 'The EP', 'total_tracks': 1})
    write_track(track)

    rendered = pane(preview, track_dir)

    assert '  Album       The EP (1975)\n' in rendered + '\n'
    # Still no position, since one of one is not a position.
    assert 'Track' not in rendered


def test_says_nothing_about_the_album_artist_of_a_single(
    preview, track_dir, cache_track, write_track
):
    """
    The album-artist row is the compilation tell. A single has no compilation
    to reveal, so a differing album artist there is a featured credit -- which
    the line under the title already carries.
    """
    track = cache_track(name='Sunset Lover')
    track['album'].update(
        {'name': 'Sunset Lover', 'total_tracks': 1, 'artists': [{'name': 'Someone Else'}]}
    )
    write_track(track)

    assert 'Album by' not in pane(preview, track_dir)


def test_stacks_the_values_in_a_narrow_pane(preview, track_dir, cache_track):
    """
    Under the threshold the label column costs more room than it explains, so
    it goes and the values keep their order and their groups.
    """
    cache_track()

    assert pane(preview, track_dir, width=40) == (
        '  Song\n'
        '  Artist\n'
        '\n'
        '  Album (1975)\n'
        '  1 of 12\n'
        '  3:35\n'
        '\n'
        '  Road Trip\n'
        '  3 April 2019 · 7 years ago'
    )


def test_says_so_when_the_track_is_not_cached(preview, track_dir):
    """A track dropped from a playlist upstream, or a cache mid-rebuild."""
    assert pane(preview, track_dir) == '  track not in cache'


def test_omits_the_length_of_a_track_cached_before_duration_was_kept(
    preview, track_dir, cache_track, write_track
):
    """
    The pre-re-cache path: until the user runs -U the field is simply absent,
    and a labelled blank is how a pane looks broken.
    """
    track = cache_track()
    del track['duration_ms']
    write_track(track)

    rendered = pane(preview, track_dir)

    assert 'Length' not in rendered
    assert 'Track       1 of 12' in rendered


def test_shows_a_bare_track_number_without_the_album_total(
    preview, track_dir, cache_track, write_track
):
    track = cache_track()
    del track['album']['total_tracks']
    write_track(track)

    assert '  Track       1\n' in pane(preview, track_dir) + '\n'


def test_omits_the_year_from_an_album_without_a_release_date(
    preview, track_dir, cache_track, write_track
):
    track = cache_track()
    del track['album']['release_date']
    write_track(track)

    assert '  Album       Album\n' in pane(preview, track_dir) + '\n'


@pytest.mark.parametrize('release_date', ['1975', '1975-11', '1975-11-21'])
def test_reads_the_year_from_every_release_date_precision(preview, release_date):
    """
    Spotify sends all three shapes and release_date_precision is not cached,
    because the first four characters are the year in each of them.
    """
    assert preview.release_year(release_date) == '1975'


@pytest.mark.parametrize('release_date', ['', None, 'soon', '19'])
def test_ignores_a_release_date_it_cannot_read(preview, release_date):
    assert preview.release_year(release_date) == ''


@pytest.mark.parametrize('added_at', ['', 'not a date', '2019-04-03T10:00:00+bad'])
def test_omits_the_added_row_without_a_usable_date(
    preview, track_dir, cache_track, added_at
):
    cache_track()

    rendered = pane(preview, track_dir, added_at=added_at)

    assert 'Added' not in rendered
    # The rest of the group survives, blank line and all.
    assert rendered.endswith('  Playlist    Road Trip')


@pytest.mark.parametrize(
    'days_ago,expected',
    [
        (0, 'today'),
        (1, 'yesterday'),
        (3, '3 days ago'),
        (10, '1 week ago'),
        (20, '2 weeks ago'),
        (60, '2 months ago'),
        (400, '1 year ago'),
        (2200, '6 years ago'),
    ],
)
def test_reads_the_interval_the_way_a_person_would(preview, days_ago, expected):
    moment = NOW - datetime.timedelta(days=days_ago)

    assert preview.format_relative(moment, NOW) == expected


def test_says_nothing_about_a_date_in_the_future(preview):
    """A clock askew is not worth a wrong sentence in the pane."""
    assert preview.format_relative(NOW + datetime.timedelta(days=2), NOW) == ''


@pytest.mark.parametrize(
    'milliseconds,expected',
    [(355000, '5:55'), (59000, '0:59'), (3723000, '1:02:03')],
)
def test_formats_a_duration(preview, milliseconds, expected):
    assert preview.format_duration(milliseconds) == expected


@pytest.mark.parametrize('milliseconds', [None, '355000', -1, True])
def test_ignores_a_duration_it_cannot_use(preview, milliseconds):
    assert preview.format_duration(milliseconds) == ''


def test_counts_the_artists_that_do_not_fit(preview, track_dir, cache_track):
    """
    Cutting mid-name loses the fact that it is a collaboration; a count keeps
    it. The pane is for recall, and 'and four others' is recall.
    """
    cache_track(
        artists=[{'name': name} for name in ('Alpha', 'Bravo', 'Charlie', 'Delta')]
    )

    rendered = pane(preview, track_dir, width=24)

    assert rendered.splitlines()[1] == '  Alpha, Bravo, +2 more'


def test_truncates_a_single_artist_too_long_for_the_pane(preview):
    assert preview.join_names(['A' * 40], 10) == 'AAAAAAAAA…'


def test_keeps_a_name_carrying_a_newline_on_one_line(preview, track_dir, cache_track):
    """
    One row is one line. A name that opened a second would push every row
    below it out of its group.
    """
    cache_track(name='First\nSecond')

    rendered = pane(preview, track_dir)

    assert rendered.splitlines()[0] == '  First Second'


@pytest.mark.parametrize(
    'name',
    [
        'A Really Very Long Song Title Indeed',
        # Twice as wide as len() reports, and a real library holds plenty.
        'ホワイル・マイ・レディ・スリープス',
    ],
)
def test_never_widens_a_row_past_the_pane(
    preview, track_dir, cache_track, write_track, name
):
    """
    fzf does not wrap the preview, it clips it, so a row wider than the pane is
    a row with its end missing and no sign that anything is gone.
    """
    track = cache_track(name=name)
    track['album']['name'] = 'An Album With A Long Name As Well'
    write_track(track)

    for width in (12, 20, 46, 80):
        for line in pane(preview, track_dir, width=width).splitlines():
            assert preview.display_width(line) <= width


def test_measures_a_name_in_columns_not_characters(preview):
    """
    len() is not a width: a CJK title takes two columns per character, and a
    combining mark none at all.
    """
    assert preview.display_width('クロッシングス') == 14
    assert preview.display_width('Album') == 5
    assert preview.display_width('e\u0301') == 1


def test_truncates_a_double_width_name_on_a_column_boundary(preview):
    """
    Cutting by characters would leave the row a column over the edge, which is
    the failure this exists to prevent: the last kept character must fit whole.
    """
    truncated = preview.truncate('ホワイル・マイ・レディ', 10)

    assert preview.display_width(truncated) <= 10
    assert truncated.endswith('…')


def test_colours_the_title_block_unless_no_color_is_set(preview, track_dir, cache_track):
    """
    fzf runs the preview on a pipe, so isatty() is False even though the pane
    is a terminal -- NO_COLOR is the only signal worth reading.
    """
    cache_track()
    bold, dim = preview.styles({})
    track = preview.load_track(track_dir, 'track-1')

    coloured = preview.render(track, 'Road Trip', ADDED_AT, 100, bold, dim, NOW)

    assert coloured.startswith('  \033[1mSong\033[0m')
    assert '\033[2mArtist\033[0m' in coloured
    assert '\033[' not in pane(preview, track_dir)


def test_reads_the_width_fzf_exports(preview):
    """FZF_PREVIEW_COLUMNS is the pane's width, which is not the terminal's."""
    assert preview.columns({'FZF_PREVIEW_COLUMNS': '64', 'COLUMNS': '200'}) == 64
    assert preview.columns({'COLUMNS': '120'}) == 120
    assert preview.columns({'FZF_PREVIEW_COLUMNS': 'wide'}) == preview.DEFAULT_COLUMNS
    assert preview.columns({}) == preview.DEFAULT_COLUMNS


def run_preview(args, env=None):
    """As fzf runs it: a subprocess, with the pane on a pipe."""
    environment = {
        'PATH': os.environ.get('PATH', ''),
        'NO_COLOR': '1',
        'FZF_PREVIEW_COLUMNS': '100',
    }
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, PREVIEW_PATH] + list(args),
        capture_output=True,
        text=True,
        env=environment,
    )


def test_runs_as_a_script(preview, track_dir, cache_track):
    cache_track()

    result = run_preview([track_dir, 'track-1', 'Road Trip', ADDED_AT])

    assert result.returncode == 0
    assert result.stderr == ''
    # Same layout as the golden pane above, modulo today's relative date.
    assert result.stdout.startswith(
        '  Song\n  Artist\n\n  Album       Album (1975)\n  Track       1 of 12\n'
    )
    assert result.stdout.endswith('\n')


@pytest.mark.parametrize(
    'args',
    [
        [],
        ['/nonexistent'],
        ['/nonexistent', 'track-1', 'Road Trip', 'nonsense'],
    ],
)
def test_never_exits_non_zero_or_prints_a_traceback(args):
    """
    There is nowhere for an error to go: fzf shows this output and nothing
    else, so a traceback would be the pane.
    """
    result = run_preview(args)

    assert result.returncode == 0
    assert result.stderr == ''
    assert 'Traceback' not in result.stdout


def test_does_not_import_spotipy_or_the_package(tmp_path, track_dir, cache_track):
    """
    The renderer runs on every cursor move, and importing the spotifz package
    reaches spotipy: 155 ms against the 42 ms this costs now. Poison both on
    the import path so an innocent-looking `from .sink import ...` fails the
    suite rather than quietly making the pane four times slower.
    """
    cache_track()
    poison = tmp_path / 'poison'
    poison.mkdir()
    for name in ('spotipy', 'spotifz'):
        (poison / (name + '.py')).write_text(
            "raise ImportError('the preview must not import {}')\n".format(name)
        )

    result = run_preview(
        [track_dir, 'track-1', 'Road Trip', ADDED_AT],
        env={'PYTHONPATH': str(poison)},
    )

    assert result.returncode == 0
    assert result.stderr == ''
    assert result.stdout.startswith('  Song\n')

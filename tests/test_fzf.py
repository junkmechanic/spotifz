import json
import os
import shlex
import subprocess

import pytest

from spotifz.helpers import fzf
from spotifz.helpers.fzf import (
    FzfNotFound,
    ensure_fzf,
    preview_command,
    run_fzf,
    run_fzf_sink,
)
from spotifz.spotify.sink import (
    ADDED_AT_FIELD,
    DISPLAY_FIELD,
    PLAYLIST_NAME_FIELD,
    SEPARATOR,
    TRACK_ID_FIELD,
)

LINE = SEPARATOR.join(
    (
        'Song One :: Album :: A, B :: Road Trip',
        'track-1',
        'pl-1',
        'Road Trip',
        '2019-04-03T10:00:00Z',
    )
)


@pytest.fixture
def fake_fzf(monkeypatch):
    """
    Stands in for the fzf binary, which blocks forever without a TTY.

    The fake *drains its stdin*. run_fzf_sink hands the FIFO's read end to
    subprocess.run, so a mock that returns without reading lets the read end
    close while the writer thread is still going, and every test sees a
    spurious BrokenPipeError. Tests that want a broken pipe use the
    non-draining fake below instead.
    """
    calls = []

    def _run(cmd, **kwargs):
        stdin = kwargs.get('stdin')
        piped = stdin.read() if stdin is not None else None
        calls.append({'cmd': cmd, 'stdin': piped, 'input': kwargs.get('input')})
        # run_fzf asks for text=True and reads stdout as str; run_fzf_sink does
        # not and decodes it itself.
        out = 'chosen line\n' if kwargs.get('text') else b'chosen line\n'
        return subprocess.CompletedProcess(cmd, 0, stdout=out)

    monkeypatch.setattr(fzf.subprocess, 'run', _run)
    return calls


@pytest.fixture
def undrained_fzf(monkeypatch):
    """The same fake, deliberately not reading stdin."""

    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 130, stdout=b'\n')

    monkeypatch.setattr(fzf.subprocess, 'run', _run)


def writer(config, fifo_path):
    with open(fifo_path, 'w') as sink:
        sink.write('one\ntwo\n')


def as_fzf_would(preview, line):
    """
    Emulates fzf's placeholder substitution: `{N}` becomes the Nth
    SEPARATOR-separated field of the original line, single-quoted. Verified by
    hand against fzf 0.74.1 -- the suite must never reach the real binary,
    which blocks forever without a TTY.
    """
    fields = line.split(SEPARATOR)
    for index, field in enumerate(fields, start=1):
        preview = preview.replace('{%d}' % index, shlex.quote(field))
    return preview


def render_preview(track_dir, line, track_id='track-1', name='Song One'):
    """
    Actually runs the preview command. Nothing else in the suite does, so a
    preview broken by a bad interpreter name, a quoting slip or a changed field
    index would otherwise ship green.
    """
    os.makedirs(track_dir, exist_ok=True)
    with open(os.path.join(track_dir, track_id), 'w') as ofile:
        json.dump(
            {
                'id': track_id,
                'name': name,
                'track_number': 1,
                'duration_ms': 215000,
                'artists': [{'name': 'A'}],
                'album': {'name': 'Album', 'release_date': '1975', 'total_tracks': 12},
            },
            ofile,
        )

    return subprocess.run(
        as_fzf_would(preview_command(track_dir), line),
        shell=True,
        capture_output=True,
        text=True,
        env=dict(os.environ, NO_COLOR='1', FZF_PREVIEW_COLUMNS='100'),
    )


def test_the_preview_command_renders_the_pane(config):
    result = render_preview(config['data_paths']['track_path'], LINE)

    assert result.returncode == 0
    assert result.stderr == ''
    assert 'Song One' in result.stdout
    # The pane, not the file: the JSON dump had none of these.
    assert 'Album       Album (1975)' in result.stdout
    assert 'Length      3:35' in result.stdout


def test_the_preview_command_passes_the_pair_fields_from_the_line(config):
    """
    The playlist name and added_at are on the line and nowhere else -- if the
    placeholders were wrong these two rows would silently disappear.
    """
    result = render_preview(config['data_paths']['track_path'], LINE)

    assert 'Playlist    Road Trip' in result.stdout
    assert 'Added       3 April 2019' in result.stdout


def test_the_preview_command_is_one_process(config):
    """
    The pipe into `(highlight ... || cat)` is gone with the JSON dump. fzf runs
    the preview under $SHELL, and that subshell is a syntax error in fish.
    """
    preview = preview_command(config['data_paths']['track_path'])

    assert '|' not in preview
    assert '(' not in preview


def test_the_preview_command_survives_a_space_in_the_path(config, tmp_path):
    """
    The old command interpolated the directory unquoted and piped it through
    xargs, which split it on whitespace.
    """
    result = render_preview(str(tmp_path / 'cache dir' / 'tracks'), LINE)

    assert 'Song One' in result.stdout


def test_the_preview_command_renders_a_track_whose_name_holds_the_separator(config):
    """
    The bug item 7 fixes, asserted from the preview's side: this used to add a
    field, so the hard-coded sixth one was the playlist id and the pane
    silently showed nothing.
    """
    line = SEPARATOR.join(
        (
            'Intro :: Reprise :: Album :: A, B :: Road Trip',
            'track-1',
            'pl-1',
            'Road Trip',
            '2019-04-03T10:00:00Z',
        )
    )

    result = render_preview(config['data_paths']['track_path'], line)

    assert 'Song One' in result.stdout


def test_the_preview_renderer_is_where_fzf_is_told_to_look():
    """
    fzf reports nothing when the command behind a pane fails, so a renderer
    that has moved shows up as an empty pane and nothing else. The path is
    built by hand from this file's location, which is exactly the kind of thing
    a directory move breaks silently.
    """
    assert os.path.exists(fzf.PREVIEW_RENDERER), fzf.PREVIEW_RENDERER


def test_ensure_fzf_passes_when_fzf_is_on_the_path(monkeypatch):
    monkeypatch.setattr(fzf.shutil, 'which', lambda name: '/usr/bin/fzf')
    ensure_fzf()


def test_ensure_fzf_raises_when_fzf_is_missing(monkeypatch):
    monkeypatch.setattr(fzf.shutil, 'which', lambda name: None)
    with pytest.raises(FzfNotFound):
        ensure_fzf()


def test_run_fzf_passes_candidates_on_stdin(fake_fzf):
    selected = run_fzf(['a', 'b'], prompt='[Test] > ')

    assert fake_fzf[0]['input'] == 'a\nb'
    assert fake_fzf[0]['cmd'] == ['fzf', '--prompt', '[Test] > ']
    assert selected == ['chosen line']


def test_run_fzf_returns_a_row_exactly_as_it_offered_it(monkeypatch):
    """
    A caller that numbers its rows pads the narrow ones so they line up, and
    then matches the selection back against what it showed. fzf returns the
    line untouched, so anything trimmed here is a row its own caller can no
    longer recognise.
    """
    row = ' 1  Song A :: Album :: Artist  (2h ago)'

    def _run(cmd, **kwargs):
        # What fzf actually writes: the chosen line and a newline.
        return subprocess.CompletedProcess(cmd, 0, stdout=row + '\n')

    monkeypatch.setattr(fzf.subprocess, 'run', _run)

    assert run_fzf([row, '10  Song J :: Album :: Artist  (3d ago)']) == [row]


def test_run_fzf_reads_an_abandoned_search_as_an_empty_selection(monkeypatch):
    """Esc: fzf writes nothing, and every caller tests for ''."""

    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 130, stdout='')

    monkeypatch.setattr(fzf.subprocess, 'run', _run)

    assert run_fzf(['a', 'b']) == ['']


def test_run_fzf_defaults_the_prompt(fake_fzf):
    run_fzf(['a'])

    assert fake_fzf[0]['cmd'] == ['fzf', '--prompt', '> ']


def test_run_fzf_sink_returns_the_selection(config, fake_fzf):
    assert run_fzf_sink(writer, config) == ['chosen line']
    assert fake_fzf[0]['stdin'] == 'one\ntwo\n'


def test_run_fzf_sink_asks_fzf_to_extract_the_id_field(config, fake_fzf):
    """
    The preview no longer parses the line itself: fzf is told the structure and
    substitutes the field.
    """
    run_fzf_sink(writer, config)

    cmd = fake_fzf[0]['cmd']
    assert cmd[cmd.index('--delimiter') + 1] == SEPARATOR
    assert cmd[cmd.index('--with-nth') + 1] == str(DISPLAY_FIELD)

    preview = cmd[cmd.index('--preview') + 1]
    assert config['data_paths']['track_path'] in preview
    for field in (TRACK_ID_FIELD, PLAYLIST_NAME_FIELD, ADDED_AT_FIELD):
        assert '{%d}' % field in preview


def test_run_fzf_sink_removes_the_fifo_on_the_normal_path(config, fake_fzf):
    run_fzf_sink(writer, config)

    assert not os.path.exists(os.path.join(config['cache_path'], 'fzf_fifo'))


def test_run_fzf_sink_removes_the_fifo_when_the_iterator_raises(config, fake_fzf):
    def raising(config, fifo_path):
        # Open and close first, or the reader blocks on open() forever.
        with open(fifo_path, 'w'):
            pass
        raise RuntimeError('sinking failed')

    with pytest.raises(RuntimeError, match='sinking failed'):
        run_fzf_sink(raising, config)

    assert not os.path.exists(os.path.join(config['cache_path'], 'fzf_fifo'))


def test_run_fzf_sink_replaces_a_stale_fifo(config, fake_fzf):
    fifo_path = os.path.join(config['cache_path'], 'fzf_fifo')
    # A leftover regular file from a previous crashed run would make mkfifo
    # fail with EEXIST.
    with open(fifo_path, 'w') as stale:
        stale.write('leftover')

    assert run_fzf_sink(writer, config) == ['chosen line']
    assert not os.path.exists(fifo_path)


def test_run_fzf_sink_removes_the_fifo_when_fzf_closes_early(config, undrained_fzf):
    """
    fzf exiting before the writer finishes surfaces as a BrokenPipeError from
    the sink thread. Whatever escapes, the FIFO must not be left behind.
    """

    def flooding(config, fifo_path):
        with open(fifo_path, 'w') as sink:
            for i in range(20000):
                sink.write('line {}\n'.format(i))
                sink.flush()

    with pytest.raises(BrokenPipeError):
        run_fzf_sink(flooding, config)

    assert not os.path.exists(os.path.join(config['cache_path'], 'fzf_fifo'))

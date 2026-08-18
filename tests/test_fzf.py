import os
import subprocess

import pytest

from spotifz.helpers import fzf
from spotifz.helpers.fzf import FzfNotFound, ensure_fzf, run_fzf, run_fzf_sink


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


def test_run_fzf_defaults_the_prompt(fake_fzf):
    run_fzf(['a'])

    assert fake_fzf[0]['cmd'] == ['fzf', '--prompt', '> ']


def test_run_fzf_sink_returns_the_selection(config, fake_fzf):
    assert run_fzf_sink(writer, config) == ['chosen line']
    assert fake_fzf[0]['stdin'] == 'one\ntwo\n'


def test_run_fzf_sink_previews_the_track_by_its_sixth_field(config, fake_fzf):
    run_fzf_sink(writer, config)

    preview = fake_fzf[0]['cmd'][fake_fzf[0]['cmd'].index('--preview') + 1]
    assert config['data_paths']['track_path'] in preview
    assert '$6' in preview


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

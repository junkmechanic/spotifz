import os
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


class FzfNotFound(Exception):
    pass


def ensure_fzf():
    if shutil.which('fzf') is None:
        raise FzfNotFound(
            'fzf was not found on your PATH. '
            'See https://github.com/junegunn/fzf for install instructions.'
        )


def preview_command(track_dir):
    """
    The shell command fzf runs for the highlighted line, with `{}` replaced by
    that line, single-quoted.

    The track id is the sixth ' :: '-separated field -- see sink_all_tracks in
    ../spotify/sink.py. A name containing ' :: ' shifts the fields and the
    preview then reads the wrong one; that is a defect of the wire format
    rather than of this command.
    """
    extract_id = "echo {} | awk -F ' :: ' '{print $6}'"
    # The directory is quoted on its own and concatenated with a double-quoted
    # command substitution, so a cache_path containing a space survives. The
    # previous version interpolated it bare and piped it through xargs, which
    # split it on whitespace.
    track_file = shlex.quote(track_dir) + '"' + os.sep + '$(' + extract_id + ')"'
    # sys.executable rather than a bare `python`: current macOS and most Linux
    # distributions ship only `python3`, and a preview that silently fails is
    # invisible -- fzf shows an empty pane and reports nothing.
    return '{} -m json.tool {} | (highlight -O ansi --syntax json || cat)'.format(
        shlex.quote(sys.executable), track_file
    )


def run_fzf(search_items, prompt=None):
    if prompt is None:
        prompt = '> '

    # fzf reads candidates from stdin, so there is no need for a shell and no
    # opportunity for the items to be reinterpreted as shell syntax.
    fuzzy_result = subprocess.run(
        ['fzf', '--prompt', prompt],
        input='\n'.join(search_items),
        text=True,
        stdout=subprocess.PIPE,
    )
    selected = fuzzy_result.stdout.strip().split('\n')
    return selected


def run_fzf_sink(iterator_func, config, prompt=None):
    fifo_path = os.path.join(config['cache_path'], 'fzf_fifo')
    if os.path.exists(fifo_path):
        os.remove(fifo_path)
    os.mkfifo(fifo_path)

    if prompt is None:
        prompt = '> '

    preview = preview_command(config['data_paths']['track_path'])

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        iterator_future = executor.submit(iterator_func, config, fifo_path)

        with open(fifo_path, 'r') as sink:
            fuzzy_result = subprocess.run(
                ['fzf', '--prompt', prompt, '--preview', preview],
                stdin=sink,
                stdout=subprocess.PIPE,
            )

        if iterator_future.exception() is not None:
            print('Something went wrong while sinking tracks!')
            raise iterator_future.exception()
    finally:
        executor.shutdown()
        if os.path.exists(fifo_path):
            os.remove(fifo_path)

    return fuzzy_result.stdout.decode().strip().split('\n')

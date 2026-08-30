import os
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

# Imported from the module rather than the package: the format's owner is
# sink.py, and spotifz.spotify may still be initialising when this is loaded.
from ..spotify.sink import (
    ADDED_AT_FIELD,
    DISPLAY_FIELD,
    PLAYLIST_NAME_FIELD,
    SEPARATOR,
    TRACK_ID_FIELD,
)

# Resolved from this file rather than from the package, and handed to the
# interpreter as a path: the renderer must not be imported, which is what
# `python -m spotifz.scripts.preview` would do. What holds that line is
# test_does_not_import_spotipy_or_the_package, not the layout -- an implicit
# namespace package imports perfectly well without an __init__.py.
PREVIEW_RENDERER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'scripts',
    'preview.py',
)


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
    The shell command fzf runs for the highlighted line.

    fzf substitutes `{N}` with the Nth SEPARATOR-separated field of the
    *original* line, single-quoted -- so there is no text parsing here at all,
    and the separator never reaches a shell. Verified against fzf 0.74.1:
    --with-nth hides the id fields from the display and from matching, but not
    from these placeholders.
    """
    # sys.executable rather than a bare `python`: current macOS and most Linux
    # distributions ship only `python3`, and a preview that silently fails is
    # invisible -- fzf shows an empty pane and reports nothing.
    return ' '.join(
        (
            shlex.quote(sys.executable),
            shlex.quote(PREVIEW_RENDERER),
            shlex.quote(track_dir),
            '{%d}' % TRACK_ID_FIELD,
            '{%d}' % PLAYLIST_NAME_FIELD,
            '{%d}' % ADDED_AT_FIELD,
        )
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
    selected = fuzzy_result.stdout.strip('\n').split('\n')
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
                [
                    'fzf',
                    '--prompt',
                    prompt,
                    # Show and match only the display field; the ids ride along
                    # on the line for the preview and for the accepted result.
                    '--delimiter',
                    SEPARATOR,
                    '--with-nth',
                    str(DISPLAY_FIELD),
                    '--preview',
                    preview,
                ],
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

    # strip('\n'), not strip(): 0x1f is whitespace to Python, so a bare strip
    # would eat a separator next to an empty field.
    return fuzzy_result.stdout.decode().strip('\n').split('\n')

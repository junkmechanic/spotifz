import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor


class FzfNotFound(Exception):
    pass


def ensure_fzf():
    if shutil.which('fzf') is None:
        raise FzfNotFound(
            'fzf was not found on your PATH. '
            'See https://github.com/junegunn/fzf for install instructions.'
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

    track_dir = config['data_paths']['track_path']

    # The `$6` refers to the 6th element separated by `::` which is `track_id`
    # Refer to function `sink_all_tracks()` in `../spotify/sink.py`
    awk_cmd = 'awk -F " :: " -v tp={}/'.format(track_dir) + " '{ print tp$6 }'"
    preview_template = """
    echo {} |
    {} |
    xargs python -m json.tool |
    (highlight -O ansi --syntax json || cat )
    """
    preview = preview_template.format('{}', awk_cmd)

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

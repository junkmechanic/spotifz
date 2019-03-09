import os
import subprocess
from concurrent.futures import ThreadPoolExecutor


def run_fzf(search_items):
    cmd = bytes("echo '{}' | fzf".format('\n'.join(search_items)), 'utf-8')
    fuzzy_result = subprocess.run(
        [cmd],
        # this is required as fzf needs a shell process and this child process
        # needs to inherit the input and output streams
        shell=True,
        # to capture the output in the parent process
        stdout=subprocess.PIPE,
    )
    selected = fuzzy_result.stdout.decode().strip().split('\n')
    return selected


def run_piped_fzf(iterator_func, config):
    fifo_path = os.path.join(config['cache_path'], 'fzf_fifo')
    if os.path.exists(fifo_path):
        os.remove(fifo_path)
    os.mkfifo(fifo_path)

    executor = ThreadPoolExecutor(max_workers=1)
    iterator_future = executor.submit(iterator_func, config, fifo_path)

    preview = '''
    echo {} |
    awk -F " :: " -v tp=/home/ankur/\.cache/spotifz/spotify_data/tracks/ '{ print tp$5 }' |
    xargs python -m json.tool |
    (highlight -O ansi --syntax json || cat )
    '''

    with open(fifo_path, 'r') as sink:
        fuzzy_result = subprocess.run(
            ['fzf', '--preview', preview],
            stdin=sink,
            stdout=subprocess.PIPE
        )

    if iterator_future.exception() is not None:
        raise iterator_future.exception()
    executor.shutdown()
    os.remove(fifo_path)

    return fuzzy_result.stdout.decode().strip().split('\n')

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

    with open(fifo_path, 'r') as sink:
        fuzzy_result = subprocess.run(
            ['fzf'],
            stdin=sink,
            stdout=subprocess.PIPE
        )

    if iterator_future.exception() is not None:
        raise iterator_future.exception()
    executor.shutdown()
    os.remove(fifo_path)

    return fuzzy_result.stdout.decode().strip().split('\n')

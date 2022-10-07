import os
import subprocess
from concurrent.futures import ThreadPoolExecutor


def run_fzf(search_items, prompt=None):
    if prompt is None:
        prompt = '> '

    cmd_template = "echo '{items}' | fzf --prompt='{prompt}' "
    cmd = cmd_template.format(items=('\n'.join(search_items)), prompt=prompt)
    fuzzy_result = subprocess.run(
        [bytes(cmd, 'utf-8')],
        # this is required as fzf needs a shell process and this child process
        # needs to inherit the input and output streams
        shell=True,
        # to capture the output in the parent process
        stdout=subprocess.PIPE,
    )
    selected = fuzzy_result.stdout.decode().strip().split('\n')
    return selected


def run_fzf_sink(iterator_func, config, prompt=None):
    fifo_path = os.path.join(config['cache_path'], 'fzf_fifo')
    if os.path.exists(fifo_path):
        os.remove(fifo_path)
    os.mkfifo(fifo_path)

    if prompt is None:
        prompt = '> '

    executor = ThreadPoolExecutor(max_workers=1)
    iterator_future = executor.submit(iterator_func, config, fifo_path)

    cache_path = os.path.expanduser(config['cache_path'])
    track_dir = os.path.join(cache_path, 'spotify_data/tracks/')

    # The `$6` refers to the 6th element separated by `::` which is `track_id`
    # Refer to function `sink_all_tracks()` in `../spotify/sink/py`
    awk_cmd = 'awk -F " :: " -v tp={}'.format(track_dir) + " '{ print tp$6 }'"
    preview_template = """
    echo {} |
    {} |
    xargs python -m json.tool |
    (highlight -O ansi --syntax json || cat )
    """
    preview = preview_template.format('{}', awk_cmd)

    with open(fifo_path, 'r') as sink:
        fuzzy_result = subprocess.run(
            ['fzf', '--prompt', prompt, '--preview', preview],
            stdin=sink,
            stdout=subprocess.PIPE,
        )

    if iterator_future.exception() is not None:
        print('Something went wrong while sinking tracks!')
        raise iterator_future.exception()
    executor.shutdown()
    os.remove(fifo_path)

    return fuzzy_result.stdout.decode().strip().split('\n')

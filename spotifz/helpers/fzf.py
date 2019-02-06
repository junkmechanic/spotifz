import subprocess

def run_fzf(search_items):
    # TODO: include fzf options. for eg. when adding multiple songs to a
    # playlist

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

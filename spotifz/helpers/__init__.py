import os

from .fzf import run_fzf


def get_expanded_path(path_str, append=None):
    expanded_path = os.path.expanduser(path_str)
    if append is not None:
        expanded_path = os.path.join(expanded_path, append)
    return expanded_path

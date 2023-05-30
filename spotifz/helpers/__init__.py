import os


def get_expanded_path(path_str, append=None):
    expanded_path = os.path.expanduser(path_str)
    if append is not None:
        expanded_path = os.path.join(expanded_path, append)
    return expanded_path


def update_data_paths(config):
    """
    Helper function returning paths
    """
    config['cache_path'] = get_expanded_path(config['cache_path'])

    data_path = os.path.join(config['cache_path'], 'spotify_data')
    config['data_paths'] = {
        'base_path': data_path,
        'playlist_path': os.path.join(data_path, 'playlists'),
        'track_path': os.path.join(data_path, 'tracks'),
        'album_path': os.path.join(data_path, 'albums'),
    }

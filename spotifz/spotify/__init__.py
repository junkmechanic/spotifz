import os
import shutil

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOauthError

from .auth import get_access_token
from .download import backup_data, cache_playlists, get_data_path


def get_spotify_client(config):
    try:
        return Spotify(auth=get_access_token(config))
    except SpotifyOauthError:
        return None


def update_cache(config, backup=True):
    if backup:
        backup_path = backup_data(config)
        if backup_path is None:
            print('No existing cache data to backup.')
        else:
            print('Existing cache backed-up to : {}'.format(backup_path))
    if os.path.exists(get_data_path(config)):
        shutil.rmtree(get_data_path(config))
        print('Deleted existing cache.')
    sp = get_spotify_client(config)
    cache_playlists(sp, config)
    print('Playlists data updated.')

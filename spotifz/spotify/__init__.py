import os
import json
import shutil
from glob import glob

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


def sink_all_tracks(config, fifo_path):
    data_path = get_data_path(config)
    with open(fifo_path, 'w') as sink:
        for p_file in glob(data_path + '/*[!.json]'):
            with open(p_file) as ifi:
                playlist = json.load(ifi)
            [
                sink.write(
                    '{name} :: {album[name]} :: {artist_list} :: {pl} :: {id}\n'
                    .format(
                        artist_list=', '.join([
                            a['name'] for a in track['artists']
                        ]),
                        pl=playlist['name'],
                        **track
                    )
                )
                for track in playlist['tracks']
            ]

import os
import traceback
from spotipy import util
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError


scope = ' '.join([
    'playlist-read-private',
    'user-modify-playback-state',
    'user-read-currently-playing',
    'user-read-playback-state',
])


def get_token_path(config):
    cache_path = os.path.expanduser(
        os.path.join(
            config['cache_path'],
            '{}_spotify.cache.json'.format(config['user'])
        ))
    return cache_path


def use_or_refresh_token(config):
    so = SpotifyOAuth(
        client_id=config['spotify_client']['client_id'],
        client_secret=config['spotify_client']['client_secret'],
        redirect_uri=config['spotify_client']['redirect_uri'],
        scope=scope,
        cache_path=get_token_path(config),
    )
    token = so.get_cached_token()
    # spotipy refreshes an expired token during the function call above
    access_token = token['access_token']

    return access_token


def user_authorize(config):
    access_token = util.prompt_for_user_token(
        username=config['user'],
        scope=scope,
        client_id=config['spotify_client']['client_id'],
        client_secret=config['spotify_client']['client_secret'],
        redirect_uri=config['spotify_client']['redirect_uri'],
        cache_path=get_token_path(config),
    )
    return access_token


def get_access_token(config):
    if os.path.exists(get_token_path(config)):
        access_token = use_or_refresh_token(config)
    else:
        try:
            access_token = user_authorize(config)
        except SpotifyOauthError as spotipy_err:
            traceback.print_exc()
            print('\nCould not get access token : {}'.format(spotipy_err))
            print('Check the traceback above to locate the source of error.')
            access_token = None

    return access_token

import os
import traceback

from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

scope = ' '.join(
    [
        'playlist-read-private',
        'user-modify-playback-state',
        'user-read-currently-playing',
        'user-read-playback-state',
    ]
)


def get_token_path(config):
    cache_path = os.path.join(
        config['cache_path'], '{}_spotify.cache.json'.format(config['user'])
    )
    return cache_path


def get_oauth(config):
    return SpotifyOAuth(
        client_id=config['spotify_client']['client_id'],
        client_secret=config['spotify_client']['client_secret'],
        redirect_uri=config['spotify_client']['redirect_uri'],
        scope=scope,
        cache_handler=CacheFileHandler(cache_path=get_token_path(config)),
    )


def use_or_refresh_token(oauth):
    # validate_token refreshes an expired token during the call below. It
    # returns None when there is nothing usable cached, and raises
    # SpotifyOauthError when the refresh token itself is rejected.
    token = oauth.validate_token(oauth.cache_handler.get_cached_token())
    if token is None:
        return None
    return token['access_token']


def user_authorize(oauth):
    return oauth.get_access_token(
        oauth.get_auth_response(), as_dict=False, check_cache=False
    )


def get_access_token(config):
    oauth = get_oauth(config)
    try:
        access_token = None
        if os.path.exists(get_token_path(config)):
            try:
                access_token = use_or_refresh_token(oauth)
            except SpotifyOauthError:
                # The cached refresh token is no longer accepted, e.g. it was
                # revoked or the app's scopes changed. Fall through to a fresh
                # authorization rather than failing outright.
                traceback.print_exc()
                print('\nCached token could not be refreshed. Re-authorizing.')
        if access_token is None:
            access_token = user_authorize(oauth)
    except SpotifyOauthError as spotipy_err:
        traceback.print_exc()
        print('\nCould not get access token : {}'.format(spotipy_err))
        print('Check the traceback above to locate the source of error.')
        access_token = None

    return access_token

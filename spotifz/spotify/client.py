from spotipy import Spotify

from .auth import get_access_token


class SpotifyAuthFailed(Exception):
    pass


def get_spotify_client(config) -> Spotify:
    access_token = get_access_token(config)
    if access_token is None:
        # get_access_token already printed the underlying error. Without this
        # check a Spotify(auth=None) client is built happily and the failure
        # resurfaces as an opaque 401 at the first API call.
        raise SpotifyAuthFailed(
            'Could not authenticate with Spotify. '
            'Check the error above, then re-run to authorize.'
        )
    return Spotify(auth=access_token)

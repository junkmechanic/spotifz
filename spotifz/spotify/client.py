from spotipy import Spotify
from spotipy.oauth2 import SpotifyOauthError

from .auth import get_access_token


def get_spotify_client(config):
    try:
        return Spotify(auth=get_access_token(config))
    except SpotifyOauthError:
        return None

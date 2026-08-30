import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


def get_expanded_path(path_str, append=None):
    expanded_path = os.path.expanduser(path_str)
    if append is not None:
        expanded_path = os.path.join(expanded_path, append)
    return expanded_path


def update_data_paths(config):
    """
    Fills in where everything the app caches lives, from the one path the user
    configures. Lives here because AppState.from_config is the only thing that
    calls it: it is the first half of normalising a config, not a utility the
    app reaches for from several places.
    """
    config['cache_path'] = get_expanded_path(config['cache_path'])

    data_path = os.path.join(config['cache_path'], 'spotify_data')
    config['data_paths'] = {
        'base_path': data_path,
        'playlist_path': os.path.join(data_path, 'playlists'),
        'track_path': os.path.join(data_path, 'tracks'),
        'album_path': os.path.join(data_path, 'albums'),
    }


# Persistence is an explicit whitelist, never asdict(self): a field holding a
# live handle (a database connection, an API client) must be addable without
# becoming a serialisation problem.
PERSISTED_FIELDS = ('active_device_id',)


@dataclass
class AppState:
    """
    One run of the app. `config` is the user's settings, normalised once at the
    boundary and thereafter read-only; everything the app *discovers* while
    running gets a field of its own.
    """

    config: Dict[str, Any]
    active_device_id: Optional[str] = None
    # Where to return after the user has picked a device. Session-only; it
    # would be actively wrong to resume last week's screen on startup.
    pending_screen: Optional[Tuple[str, tuple]] = None

    @classmethod
    def from_config(cls, config):
        # update_data_paths writes only top-level keys, so a shallow copy is
        # enough to leave the caller's dict untouched.
        normalised = dict(config)
        update_data_paths(normalised)
        state = cls(config=normalised)
        state.load()
        return state

    @property
    def cache_path(self):
        return self.config['cache_path']

    @property
    def data_paths(self):
        return self.config['data_paths']

    @property
    def state_path(self):
        # Named after the user, like the token cache in auth.get_token_path,
        # and outside spotify_data/ so `spotifz -U` does not wipe it.
        return os.path.join(self.cache_path, '{}_state.json'.format(self.config['user']))

    def load(self):
        try:
            with open(self.state_path) as ifile:
                saved = json.load(ifile)
        except (FileNotFoundError, ValueError):
            # No state yet, or a truncated file from a killed run. Session
            # state is never worth failing a launch over. json.JSONDecodeError
            # subclasses ValueError, so one except covers both.
            return
        if not isinstance(saved, dict):
            return
        for name in PERSISTED_FIELDS:
            if saved.get(name) is not None:
                setattr(self, name, saved[name])

    def save(self):
        payload = {name: getattr(self, name) for name in PERSISTED_FIELDS}
        os.makedirs(self.cache_path, exist_ok=True)
        tmp_path = self.state_path + '.tmp'
        with open(tmp_path, 'w') as ofile:
            json.dump(payload, ofile)
        # A half-written state file must not be able to break the next launch.
        os.replace(tmp_path, self.state_path)

    def set_active_device(self, device_id):
        self.active_device_id = device_id
        self.save()

    def forget_active_device(self):
        self.active_device_id = None
        self.save()

    def take_pending_screen(self):
        pending, self.pending_screen = self.pending_screen, None
        return pending

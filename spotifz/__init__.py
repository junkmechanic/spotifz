from . import spotify
from .helpers import ensure_fzf
from .interface import screens
from .state import AppState

REQUIRED_CONFIG_KEYS = (
    ('spotify_client', 'client_id'),
    ('spotify_client', 'client_secret'),
    ('spotify_client', 'redirect_uri'),
    ('cache_path',),
    ('user',),
)


class ConfigError(Exception):
    pass


def validate_config(config):
    """
    Without this, a missing key surfaces as a bare KeyError from deep inside
    the auth call.
    """
    missing = []
    for key_path in REQUIRED_CONFIG_KEYS:
        node = config
        for key in key_path:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = node[key]
        if node is None or node == '':
            missing.append('.'.join(key_path))

    if missing:
        raise ConfigError(
            'Config is missing a value for: {}\n'
            'See config.json in the project root for the expected shape.'.format(
                ', '.join(missing)
            )
        )


def prepare(config):
    validate_config(config)
    # The state normalises the config onto a copy of its own, so the dict the
    # caller loaded from JSON is never written to.
    return AppState.from_config(config)


def update_cache(config):
    state = prepare(config)
    spotify.update_cache(state.config)


def launch(config):
    state = prepare(config)
    ensure_fzf()

    # The entry point resolves through the registry like every other hop, so
    # home_screen is not a second, hard-coded way to name a screen.
    choice, screen_args = 'home_screen', []
    while choice is not None:
        upcoming_screen = screens.get_screen(choice)
        choice, *screen_args = upcoming_screen(state, *screen_args)

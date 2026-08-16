from . import spotify
from .helpers import ensure_fzf, update_data_paths
from .interface import screens

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
    # ensure that the paths are populated in the config
    update_data_paths(config)


def update_cache(config):
    prepare(config)
    spotify.update_cache(config)


def launch(config):
    prepare(config)
    ensure_fzf()

    choice, *screen_args = screens.home_screen(config)
    while choice is not None:
        upcoming_screen = getattr(screens, choice)
        choice, *screen_args = upcoming_screen(config, *screen_args)

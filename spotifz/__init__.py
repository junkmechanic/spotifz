from .helpers import get_expanded_path
from .interface import screens

def launch(config):
    # this is not as safe as sanitizing paths during usage, but its a
    # compromize given this function is the sole entrypoint fow now.
    config['cache_path'] = get_expanded_path(config['cache_path'])
    choice = screens.home_screen(config)
    while choice is not None:
        upcoming_screen = getattr(screens, choice)
        choice = upcoming_screen(config)

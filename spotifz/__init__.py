from .helpers import update_data_paths
from .interface import screens


def launch(config):
    # ensure that the paths are populated in the config
    update_data_paths(config)

    choice, *screen_args = screens.home_screen(config)
    while choice is not None:
        upcoming_screen = getattr(screens, choice)
        if isinstance(screen_args, list):
            choice, *screen_args = upcoming_screen(config, *screen_args)
        else:
            choice, *screen_args = upcoming_screen(config)

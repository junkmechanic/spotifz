from .interface import screens

def launch(config):
    choice = screens.home_screen(config)
    while choice is not None:
        upcoming_screen = getattr(screens, choice)
        choice = upcoming_screen(config)

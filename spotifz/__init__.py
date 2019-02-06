from .interface import screens

def launch(config):
    choice = 'home_screen'
    while choice is not None:
        upcoming_screen = getattr(screens, 'home_screen')
        choice = upcoming_screen()

import argparse
import json
import os
import sys

import spotifz
from spotifz.helpers import FzfNotFound
from spotifz.spotify.client import SpotifyAuthFailed


def load_config(config_path):
    path = os.path.expanduser(config_path)
    try:
        with open(path) as ifile:
            return json.load(ifile)
    except FileNotFoundError:
        raise spotifz.ConfigError(
            'No config file at {}\n'
            'Copy config.json from the project root and fill it in.'.format(path)
        )
    except json.JSONDecodeError as e:
        raise spotifz.ConfigError('Config at {} is not valid JSON: {}'.format(path, e))


def main():
    description = 'A thin spotify client for playback and library search'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        '--config-path',
        default='~/.config/spotifz.json',
        help='Alternate config file path',
    )
    parser.add_argument(
        '-U',
        '--update-cache',
        action='store_true',
        help='Update spotify cache and exit, without entering the menu',
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config_path)
        if args.update_cache:
            spotifz.update_cache(config)
        else:
            spotifz.launch(config)
    except (spotifz.ConfigError, FzfNotFound, SpotifyAuthFailed) as e:
        print(e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())

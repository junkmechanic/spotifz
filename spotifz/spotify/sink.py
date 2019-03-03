import os
import json
from glob import glob

from .storage import get_data_path


def sink_all_tracks(config, fifo_path):
    _, pl_path, _, _ = get_data_path(config, subpaths=True)
    with open(fifo_path, 'w') as sink:
        for p_file in glob(pl_path + '/*[!.json]'):
            with open(p_file) as ifi:
                playlist = json.load(ifi)
            [
                sink.write(
                    '{name} :: {album[name]} :: {artist_list} :: {pl} :: {id}\n'
                    .format(
                        artist_list=', '.join([
                            a['name'] for a in track['artists']
                        ]),
                        pl=playlist['name'],
                        **track
                    )
                )
                for track in playlist['tracks']
            ]


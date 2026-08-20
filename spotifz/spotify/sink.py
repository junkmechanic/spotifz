import json
import os
from glob import glob


def sink_all_tracks(config, fifo_path):
    song_template = (
        '{name} :: {album[name]} :: {artist_list} :: {pl} :: {pl_id} :: {id}\n'
    )

    try:
        with open(fifo_path, 'w') as sink:
            for p_file in glob(os.path.join(config['data_paths']['playlist_path'], '*')):
                with open(p_file) as ifi:
                    playlist = json.load(ifi)
                for track in playlist['tracks']:
                    sink.write(
                        song_template.format(
                            artist_list=', '.join(
                                [artist['name'] for artist in track['artists']]
                            ),
                            pl=playlist['name'],
                            pl_id=playlist['id'],
                            **track,
                        )
                    )
    except BrokenPipeError:
        # fzf was closed before every track had been written, e.g. the user
        # picked a track or hit Esc. Nothing left to sink.
        pass

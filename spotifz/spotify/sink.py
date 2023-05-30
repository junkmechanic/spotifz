import json
from glob import glob


def sink_all_tracks(config, fifo_path):
    song_template = (
        '{name} :: {album[name]} :: {artist_list} :: {pl} :: {pl_id} :: {id}\n'
    )

    with open(fifo_path, 'w') as sink:
        for p_file in glob(
            config['data_paths']['playlist_path'] + '/*[!.json]'
        ):
            with open(p_file) as ifi:
                playlist = json.load(ifi)
            [
                sink.write(
                    song_template.format(
                        artist_list=', '.join(
                            [artist['name'] for artist in track['artists']]
                        ),
                        pl=playlist['name'],
                        pl_id=playlist['id'],
                        **track
                    )
                )
                for track in playlist['tracks']
            ]

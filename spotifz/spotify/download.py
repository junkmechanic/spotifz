import os
import json
import shutil
import datetime


def get_data_path(config):
    data_path = os.path.expanduser(
        os.path.join(config['cache_path'], 'playlists')
    )
    return data_path


def iter_spotify_reponse(spotify_client, func, *func_args, **func_kwargs):
    response = getattr(spotify_client, func)(*func_args, **func_kwargs)
    while response is not None:
        yield from response['items']
        response = spotify_client.next(response)


def extract_fields(src_dict, fields):
    return {k: src_dict[k] for k in src_dict if k in fields}


def cache_playlists(spotify_client, config):
    data_path = get_data_path(config)
    if not os.path.exists(data_path):
        os.mkdir(data_path)
    # There is no need to store all the information from the response.
    for pl in iter_spotify_reponse(spotify_client, 'current_user_playlists'):
        playlist = extract_fields(pl, ['href', 'id', 'name', 'uri'])
        playlist['tracks'] = []
        for trk in iter_spotify_reponse(spotify_client,
                                        'user_playlist_tracks',
                                        spotify_client.current_user()['id'],
                                        playlist_id=pl['id']):
            track = extract_fields(trk['track'], ['artists', 'id', 'name',
                                                  'track_number', 'uri'])
            track['album'] = extract_fields(trk['track']['album'],
                                            ['artists', 'id', 'name', 'uri'])
            playlist['tracks'].append(track)
        with open(os.path.join(data_path, playlist['id']), 'w') as ofile:
            json.dump(playlist, ofile)


def backup_data(config):
    data_path = get_data_path(config)
    if not os.path.exists(data_path):
        return None

    root_dir, base_dir = os.path.dirname(data_path), os.path.basename(data_path)

    ct = datetime.datetime.today().isoformat()
    archive_name = 'playlists_{}'.format(ct)
    archive_path = os.path.join(root_dir, archive_name)

    archive_path = shutil.make_archive(archive_path, format='gztar',
                                       root_dir=root_dir, base_dir=base_dir)
    return archive_path

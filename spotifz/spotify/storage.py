import datetime
import json
import os
import shutil

from .client import get_spotify_client


def iter_spotify_reponse(spotify_client, func, *func_args, **func_kwargs):
    response = getattr(spotify_client, func)(*func_args, **func_kwargs)
    while response is not None:
        yield from response['items']
        response = spotify_client.next(response)


def extract_fields(src_dict, fields):
    # There is no need to store all the information from the response.
    return {k: src_dict[k] for k in src_dict if k in fields}


def cache_data(spotify_client, config):
    """
    Creates a directory each for albums, tracks and playlists by iterating through each
    track in every playlist defined by the user
    """
    for dir_path in config['data_paths'].values():
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

    def update_unit(unit_dir, unit, playlist_id, playlist_name):
        try:
            unit_path = os.path.join(unit_dir, unit['id'])
        except TypeError as e:
            # if a song is removed from the Spotify database, it might not have
            # an `id` attached to it
            print(f'{e}\n{unit}\n{playlist_name}\n')
            return
        if os.path.exists(unit_path):
            with open(unit_path) as ifi:
                saved_unit = json.load(ifi)
            pl_list = saved_unit['playlists']
            pl_list.append(playlist_id)
            unit['playlists'] = list(set(pl_list))
        else:
            unit['playlists'] = [playlist_id]
        with open(unit_path, 'w') as ofi:
            json.dump(unit, ofi)

    for pl in iter_spotify_reponse(spotify_client, 'current_user_playlists'):
        playlist = extract_fields(pl, ['href', 'id', 'name', 'uri'])
        playlist['tracks'] = []
        for trk in iter_spotify_reponse(
            spotify_client,
            'user_playlist_tracks',
            spotify_client.current_user()['id'],
            playlist_id=pl['id'],
        ):
            track = extract_fields(
                trk['track'], ['artists', 'id', 'name', 'track_number', 'uri']
            )
            track['album'] = extract_fields(
                trk['track']['album'], ['artists', 'id', 'name', 'uri']
            )
            playlist['tracks'].append(track)
            update_unit(
                config['data_paths']['track_path'],
                track,
                playlist['id'],
                playlist['name'],
            )
            update_unit(
                config['data_paths']['album_path'],
                track['album'],
                playlist['id'],
                playlist['name'],
            )
        with open(
            os.path.join(
                config['data_paths']['playlist_path'], playlist['id']
            ),
            'w',
        ) as ofile:
            json.dump(playlist, ofile)


def backup_data(config):
    data_path = config['data_paths']['base_path']
    if not os.path.exists(data_path):
        return None

    root_dir, base_dir = os.path.dirname(data_path), os.path.basename(
        data_path
    )

    ct = datetime.datetime.today().isoformat()
    archive_name = 'spotify_data_{}'.format(ct)
    archive_path = os.path.join(root_dir, 'backup', archive_name)

    archive_path = shutil.make_archive(
        archive_path, format='gztar', root_dir=root_dir, base_dir=base_dir
    )
    return archive_path


def update_cache(config, backup=True):
    if backup:
        backup_path = backup_data(config)
        if backup_path is None:
            print('No existing cache data to backup.')
        else:
            print('Existing cache backed-up to : {}'.format(backup_path))

    data_path = config['data_paths']['base_path']
    if os.path.exists(data_path):
        shutil.rmtree(data_path)
        print('Deleted existing cache.')

    sp = get_spotify_client(config)
    cache_data(sp, config)
    print('Playlists data updated.')

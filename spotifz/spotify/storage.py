import os
import json
import shutil
import datetime

from .client import get_spotify_client


def get_data_path(config, subpaths=False):
    data_path = os.path.join(config['cache_path'], 'spotify_data')
    if not subpaths:
        return data_path
    else:
        pl_dir = os.path.join(data_path, 'playlists')
        tr_dir = os.path.join(data_path, 'tracks')
        al_dir = os.path.join(data_path, 'albums')
        return data_path, pl_dir, tr_dir, al_dir


def iter_spotify_reponse(spotify_client, func, *func_args, **func_kwargs):
    response = getattr(spotify_client, func)(*func_args, **func_kwargs)
    while response is not None:
        yield from response['items']
        response = spotify_client.next(response)


def extract_fields(src_dict, fields):
    # There is no need to store all the information from the response.
    return {k: src_dict[k] for k in src_dict if k in fields}


def cache_data(spotify_client, config):
    for dir_path in get_data_path(config, subpaths=True):
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
    _, pl_dir, tr_dir, al_dir = get_data_path(config, subpaths=True)

    def update_unit(unit_dir, unit, playlist_id, playlist_name):
        try:
            unit_path = os.path.join(unit_dir, unit['id'])
        except TypeError as e:
            # if a song is removed from the Spotify database, it might not have
            # an `id` attached to it
            print('{error}\n{unit}\n{pl}\n'.format(dict(error=e, unit=unit,
                                                        pl=playlist_name)))
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
        for trk in iter_spotify_reponse(spotify_client,
                                        'user_playlist_tracks',
                                        spotify_client.current_user()['id'],
                                        playlist_id=pl['id']):
            track = extract_fields(trk['track'], ['artists', 'id', 'name',
                                                  'track_number', 'uri'])
            track['album'] = extract_fields(trk['track']['album'],
                                            ['artists', 'id', 'name', 'uri'])
            playlist['tracks'].append(track)
            update_unit(tr_dir, track, playlist['id'], playlist['name'])
            update_unit(al_dir, track['album'], playlist['id'], playlist['name'])
        with open(os.path.join(pl_dir, playlist['id']), 'w') as ofile:
            json.dump(playlist, ofile)


def backup_data(config):
    data_path = get_data_path(config)
    if not os.path.exists(data_path):
        return None

    root_dir, base_dir = os.path.dirname(data_path), os.path.basename(data_path)

    ct = datetime.datetime.today().isoformat()
    archive_name = 'spotify_data_{}'.format(ct)
    archive_path = os.path.join(root_dir, 'backup', archive_name)

    archive_path = shutil.make_archive(archive_path, format='gztar',
                                       root_dir=root_dir, base_dir=base_dir)
    return archive_path


def update_cache(config, backup=True):
    if backup:
        backup_path = backup_data(config)
        if backup_path is None:
            print('No existing cache data to backup.')
        else:
            print('Existing cache backed-up to : {}'.format(backup_path))
    if os.path.exists(get_data_path(config)):
        shutil.rmtree(get_data_path(config))
        print('Deleted existing cache.')
    sp = get_spotify_client(config)
    cache_data(sp, config)
    print('Playlists data updated.')

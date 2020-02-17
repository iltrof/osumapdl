from os import path
from typing import Optional
from urllib import parse

import requests

import common


class ConnectionError(Exception):
    pass


class MapsetUnavailable(Exception):
    pass


class DownloadError(Exception):
    pass


class SearchError(Exception):
    pass


def mapset_unavailable(r: requests.Response) -> bool:
    return r.ok and 'content-disposition' not in r.headers


class Downloader(common.Downloader):
    def __init__(self) -> None:
        self.sess = common.retrying_session()

    def check_availability(self, set_id: str) -> bool:
        try:
            r = self.sess.get('https://bloodcat.com/osu/',
                              params={'q': set_id, 'c': 's', 'mod': 'json'}, timeout=15)
        except requests.ConnectionError:
            raise ConnectionError(f"Couldn't connect to bloodcat.")

        if not r.ok:
            raise SearchError(f"{r.status_code} {r.reason}.\n"
                              "This might be a bug, or you might just have to try again.")

        try:
            j = r.json()
            r.close()
            return len(j) != 0
        except:
            r.close()
            raise SearchError(f"bloodcat is sending unexpected responses.\n"
                              "This is probably a bug in the script and should be reported.")

    def download_mapset(self, id: str, dest_dir: str) -> None:
        print(f'[bloodcat] Downloading mapset #{id}')
        try:
            dl = self.sess.get(f'https://bloodcat.com/osu/s/{id}', timeout=15)
        except requests.ConnectionError as e:
            raise ConnectionError(
                f"Couldn't connect to bloodcat when downloading mapset #{id}.")

        if mapset_unavailable(dl):
            raise MapsetUnavailable(
                f"Mapset #{id} doesn't exist or isn't available for download.")
        if not dl.ok:
            raise DownloadError(
                f'Failed to download mapset #{id}: {dl.status_code} {dl.reason}')

        filename = common.filename_re.search(dl.headers['content-disposition'])
        if filename is None:
            filename = f'{id}.osz'
        else:
            filename = parse.unquote(filename[1])
            filename = common.path_special_chars.sub('_', filename)

        with open(path.join(dest_dir, filename), 'wb') as f:
            f.write(dl.content)

        dl.close()


def resolve_map_id(id: str) -> Optional[str]:
    try:
        r = common.retrying_session().get(f'https://bloodcat.com/osu/',
                                          params={'q': id, 'c': 'b', 'mod': 'json'}, timeout=15)
    except requests.ConnectionError:
        raise ConnectionError(f"Couldn't connect to bloodcat.")

    if not r.ok:
        raise SearchError(f"{r.status_code} {r.reason}.\n"
                          "This might be a bug, or you might just have to try again.")

    try:
        j = r.json()
        r.close()
        if len(j) == 0:
            return None
        return str(j[0]['id'])
    except:
        r.close()
        raise SearchError(f"bloodcat is sending unexpected responses.\n"
                          "This is probably a bug in the script and should be reported.")
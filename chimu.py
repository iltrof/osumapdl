from os import path
import time
from urllib import parse

import requests

import common

rate_limit_seconds = 5.0


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
        self.time_of_last_download = 0.0

    def check_availability(self, set_id: str) -> bool:
        try:
            r = self.sess.get('https://chimu.moe/',
                              params={'q': set_id, 'c': 's', 'mod': 'json'}, timeout=15)
        except requests.ConnectionError:
            raise ConnectionError(f"Couldn't connect to chimu.")

        if not r.ok:
            raise SearchError(f"{r.status_code} {r.reason}.\n"
                              "This might be a bug, or you might just have to try again.")

        try:
            j = r.json()
            return len(j) != 0
        except:
            raise SearchError(f"chimu is sending unexpected responses.\n"
                              "This is probably a bug in the script and should be reported.")

    def download_mapset(self, id: str, dest_dir: str) -> None:
        print(f'[chimu] Downloading mapset #{id}')
        try:
            dl = self.sess.get(f'https://api.chimu.moe/v1/download/{id}?n=1', timeout=15)
        except requests.ConnectionError as e:
            raise ConnectionError(
                f"Couldn't connect to chimu when downloading mapset #{id}.")

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

        self.safe_save_to_file(dl.content, path.join(dest_dir, filename))

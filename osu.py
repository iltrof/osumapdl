from os import path
from typing import Optional

import requests

import common


class WrongCredentials(Exception):
    pass


class LoginError(Exception):
    pass


class ConnectionError(Exception):
    pass


class MapsetUnavailable(Exception):
    pass


class QuotaExceeded(Exception):
    pass


class DownloadError(Exception):
    pass


class MapResolutionError(Exception):
    pass


def wrong_credentials(r: requests.Response) -> bool:
    return r.status_code == 422


def mapset_unavailable(r: requests.Response) -> bool:
    return r.status_code == 404


def quota_exceeded(r: requests.Response) -> bool:
    return r.status_code == 403


def osu_session(username: str, password: str) -> requests.Session:
    s = common.retrying_session()
    try:
        login = s.post('https://osu.ppy.sh/session',
                       data={'username': username, 'password': password}, timeout=15)
    except requests.ConnectionError:
        raise ConnectionError(
            'All attempts to log in to osu! timed out :(')

    if not login.ok:
        if wrong_credentials(login):
            raise WrongCredentials()
        raise LoginError(
            f"Couldn't log in to osu!: {login.status_code} {login.reason}.")

    login.close()
    return s


class Downloader(common.Downloader):
    def __init__(self, with_video: bool) -> None:
        self.sess = requests.Session()
        self.with_video = with_video

    def login(self, username: str, password: str) -> None:
        self.sess = osu_session(username, password)

    def download_mapset(self, id: str, dest_dir: str) -> None:
        print(f'[osu] Downloading mapset #{id}')
        try:
            dl = self.sess.get(f'https://osu.ppy.sh/beatmapsets/{id}/download', params={
                               'noVideo': '0' if self.with_video else '1'}, timeout=15)
        except requests.ConnectionError:
            raise ConnectionError(
                f"Couldn't connect to osu! when downloading mapset #{id}.")

        if mapset_unavailable(dl):
            raise MapsetUnavailable(
                f"Mapset #{id} doesn't exist or isn't available for download.")
        if quota_exceeded(dl):
            raise QuotaExceeded()
        if not dl.ok:
            raise DownloadError(
                f'Failed to download mapset #{id}: {dl.status_code} {dl.reason}')

        filename = common.filename_re.search(dl.headers['content-disposition'])
        if filename is None:
            filename = f'{id}.osz'
        else:
            filename = common.path_special_chars.sub('_', filename[1])

        with open(path.join(dest_dir, filename), 'wb') as f:
            f.write(dl.content)

        dl.close()


def resolve_map_id(id: str) -> Optional[str]:
    try:
        r = common.retrying_session().get(f'https://osu.ppy.sh/beatmaps/{id}',
                                          allow_redirects=False, timeout=15)
    except requests.ConnectionError:
        raise MapResolutionError(f"Couldn't connect to osu!\n"
                                 "Check if the website even works and try again.")

    if r.status_code == 404:
        return None

    if not r.ok:
        raise MapResolutionError(f"{r.status_code} {r.reason}.\n"
                                 "This might be a bug, or you might just have to try again.")
    if r.status_code != 302:  # 302 FOUND
        raise MapResolutionError(f"osu! didn't redirect properly: {r.status_code} {r.reason}.\n"
                                 "This is probably a bug in the script and should be reported.")

    url = r.headers['location']
    r.close()
    match = common.mapset_url_re.search(url)
    if match is None:
        raise MapResolutionError(f"osu! redirected to {url}, which the script didn't expect.\n"
                                 "This is probably a bug in the script and should be reported.")
    return match[1]

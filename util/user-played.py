import re
import sys
import time
from typing import Optional, Set

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if len(sys.argv) not in [2, 3]:
    print('Usage: python user-played.py user [output-file]')
    exit(1)


def retrying_session(retries: int = 3, backoff: float = 2.5) -> requests.Session:
    s = requests.Session()
    s.headers['User-Agent'] = 'github.com/iltrof/osumapdl'
    retry = Retry(total=retries, read=retries,
                  connect=retries, backoff_factor=backoff,
                  status_forcelist=[429])  # 429 TOO MANY REQUESTS
    adapter = HTTPAdapter(max_retries=retry)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s


user_url_re = re.compile(r'osu\.ppy\.sh/u(?:sers)/(\d+)')


def get_user_id(user: str) -> Optional[str]:
    try:
        r = retrying_session().get(
            f'https://osu.ppy.sh/users/{user}', allow_redirects=False, timeout=10)
    except requests.ConnectionError:
        raise ConnectionError(f"Couldn't connect to osu!\n"
                              "Check if the website even works and try again.")

    if r.status_code == 404:
        return None

    if not r.ok:
        raise ConnectionError(f"osu! returned {r.status_code} {r.reason}.\n"
                              "This might be a bug, or you might just have to try again.")
    if r.status_code == 302:  # 302 FOUND
        url = r.headers['location']
        match = user_url_re.search(url)
        if match is None:
            raise RuntimeError(f"Couldn't get the user's ID by their name.\n"
                               "This is probably a bug and should be reported.")
        return match[1]

    return user


try:
    uid = get_user_id(sys.argv[1])
except Exception as e:
    print(e)
    exit(1)

if uid is None:
    print(f"There's no user known as '{sys.argv[1]}'.")
    exit(1)

out_file = sys.argv[1] + '.txt'
if len(sys.argv) == 3:
    out_file = sys.argv[2]


def get_played_mapsets(uid: str) -> Set[str]:
    offset = 0
    mapsets = set()
    sess = retrying_session()

    while True:
        print(offset, end='\r')
        try:
            r = sess.get(
                f'https://osu.ppy.sh/users/{uid}/beatmapsets/most_played?offset={offset}&limit=51', timeout=10)
        except requests.ConnectionError:
            raise ConnectionError(f"Couldn't connect to osu!\n"
                                  "Check if the website even works and try again.")

        if not r.ok:
            raise ConnectionError(f"osu! returned {r.status_code} {r.reason}.\n"
                                  "This might be a bug, or you might just have to try again.")

        try:
            j = r.json()
        except:
            raise RuntimeError(f"osu! is sending unexpected responses.\n"
                               "This is probably a bug and should be reported.")
        if len(j) == 0:
            break

        for m in j:
            mapsets.add(m['beatmapset']['id'])
        offset += 51
        time.sleep(1)

    return mapsets


print('[info] Fetching played maps, 51 at a time...')
try:
    mapsets = get_played_mapsets(uid)
except Exception as e:
    print(f'[error] {e}')
    exit(1)

print(f'[info] Found {len(mapsets)} total mapsets.')
print(f'[info] Saving to {out_file}...')
with open(out_file, 'w') as f:
    for id in mapsets:
        f.write(f'{id}\n')

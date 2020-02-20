import codecs
import re
import sys
from typing import Optional, Set

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if len(sys.argv) != 3:
    print('Usage: python from-links.py input-file output-file')
    exit(1)

mapset_url_re = re.compile(r'osu\.ppy\.sh/(?:s|beatmapsets)/(\d+)')
map_url_re = re.compile(
    r'osu\.ppy\.sh/(?:b(?:eatmaps)?|beatmapsets/\d+#osu)/(\d+)')


def retrying_session(retries: int = 3, backoff: float = 2.0) -> requests.Session:
    s = requests.Session()
    s.headers['User-Agent'] = 'github.com/iltrof/osumapdl'
    retry = Retry(total=retries, read=retries,
                  connect=retries, backoff_factor=backoff,
                  status_forcelist=[429])  # 429 TOO MANY REQUESTS
    adapter = HTTPAdapter(max_retries=retry)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s


def resolve_map_id_osu(id: str) -> Optional[str]:
    try:
        r = retrying_session().get(f'https://osu.ppy.sh/beatmaps/{id}',
                                   allow_redirects=False, timeout=15)
    except requests.ConnectionError:
        raise ConnectionError(f"Couldn't connect to osu!\n"
                              "Check if the website even works and try again.")

    if r.status_code == 404:
        return None

    if not r.ok:
        raise ConnectionError(f"{r.status_code} {r.reason}.\n"
                              "This might be a bug, or you might just have to try again.")
    if r.status_code != 302:  # 302 FOUND
        raise RuntimeError(f"osu! didn't redirect properly: {r.status_code} {r.reason}.\n"
                           "This is probably a bug in the script and should be reported.")

    url = r.headers['location']
    match = mapset_url_re.search(url)
    if match is None:
        raise RuntimeError(f"osu! redirected to {url}, which the script didn't expect.\n"
                           "This is probably a bug in the script and should be reported.")
    return match[1]


def resolve_map_id_bloodcat(id: str) -> Optional[str]:
    try:
        r = retrying_session().get(f'https://bloodcat.com/osu/',
                                   params={'q': id, 'c': 'b', 'mod': 'json'}, timeout=15)
    except requests.ConnectionError:
        raise ConnectionError(f"Couldn't connect to bloodcat.")

    if not r.ok:
        raise ConnectionError(f"{r.status_code} {r.reason}.\n"
                              "This might be a bug, or you might just have to try again.")

    try:
        j = r.json()
        if len(j) == 0:
            return None
        return str(j[0]['id'])
    except:
        raise RuntimeError(f"bloodcat is sending unexpected responses.\n"
                           "This is probably a bug in the script and should be reported.")


def resolve_map_id(id: str) -> Optional[str]:
    set_id = None
    bloodcat_error = None
    try:
        set_id = resolve_map_id_bloodcat(id)
    except Exception as e:
        bloodcat_error = e

    if bloodcat_error is None and set_id is not None:
        return set_id

    try:
        return resolve_map_id_osu(id)
    except Exception as e:
        raise RuntimeError(bloodcat_error, e)


with codecs.open(sys.argv[1], 'r', 'utf-8') as f:
    content = f.read()

mapsets: Set[str] = set(mapset_url_re.findall(content))
content = mapset_url_re.sub('', content)
maps: Set[str] = set(map_url_re.findall(content))

print(f'Found {len(mapsets)} links to mapsets and {len(maps)} links to maps.')
if len(maps) > 0:
    print(f'Resolving {len(maps)} links to maps...')

    for i, id in enumerate(maps):
        print(f'{i+1} / {len(maps)}', end='\r')
        try:
            set_id = resolve_map_id(id)
            if set_id is None:
                print(f"\nMap #{id} doesn't exist")
                continue
            mapsets.add(set_id)
        except RuntimeError as e:
            print(f'\nFailed to look up map #{id}.\n'
                  f'[bloodcat] {e.args[0][0]}\n'
                  f'[osu] {e.args[0][0]}')
            exit(1)

    print('')
    print(f'Collected a total of {len(mapsets)} mapsets.')

print(f'Writing to {sys.argv[2]}...')
with open(sys.argv[2], 'w') as f:
    for id in mapsets:
        f.write(id + '\n')

print('Done!')

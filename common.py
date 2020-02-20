from multiprocessing import Queue
import re
from typing import Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

filename_re = re.compile('filename="(.*)"')
path_special_chars = re.compile(r'[<>:"/\\|?*]')
mapset_url_re = re.compile(r'osu\.ppy\.sh/(?:s|beatmapsets)/(\d+)')
map_url_re = re.compile(
    r'osu\.ppy\.sh/(?:b(?:eatmaps)?|beatmapsets/\d+#(?:osu|taiko|fruits|mania))/(\d+)')


def retrying_session(retries: int = 10, backoff: float = 0.2) -> requests.Session:
    s = requests.Session()
    retry = Retry(total=retries, read=retries,
                  connect=retries, backoff_factor=backoff,
                  status_forcelist=[429, 503])  # 429 TOO MANY REQUESTS, 503 SERVICE UNAVAILABLE
    adapter = HTTPAdapter(max_retries=retry)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s


class Downloader:
    def download_mapset(self, id: str, dest_dir: str) -> None:
        pass

    def download_mapsets(
        self,
        name: str,
        dest_dir: str,
        in_queue: 'Queue[str]',
        out_queue: 'Queue[Tuple[str, str, Optional[Exception]]]',
    ) -> None:
        while True:
            id = in_queue.get()
            if id == 'stop':
                return

            try:
                self.download_mapset(id, dest_dir)
            except Exception as e:
                out_queue.put((name, id, e))
            else:
                out_queue.put((name, id, None))

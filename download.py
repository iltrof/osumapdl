import argparse
import configparser
import json
from multiprocessing import Process, Queue
import os
import sys
import time
import traceback
from typing import Optional, Set, Tuple

import bloodcat
import messages
import osu

parser = argparse.ArgumentParser(usage='%(prog)s [options] ids_file')
parser.add_argument('--cfg', dest='cfg_file', metavar='cfg-file',
                    action='store', help='config file to use', default='dlconfig.ini')
parser.add_argument('ids_file', action='store',
                    help='file with IDs of mapsets you want downloaded')
parser.add_argument('-o', '--out', action='store', dest='out_dir', metavar='out-dir',
                    default='downloads', help='folder to download files into')
parser.add_argument('--max-errors', action='store', dest='max_errors_in_a_row', type=int, metavar='N',
                    default=5, help='errors in a row to tolerate before killing the script')

osu_args = parser.add_argument_group('osu', 'osu-related arguments')
osu_args.add_argument('--osu', dest='use_osu', action='store_true',
                      help='enables downloading via osu!')
osu_args.add_argument('--no-osu', dest='use_osu',
                      action='store_false', help='disables downloading via osu!')
osu_args.add_argument('--username', dest='osu_username', metavar='osu-name',
                      action='store', help='your osu! username')
osu_args.add_argument('--password', dest='osu_password', metavar='osu-pw',
                      action='store', help='your osu! password')
osu_args.add_argument('--video', dest='with_video', action='store_true',
                      help='downloads maps with video whenever possible (only for osu, not bloodcat)')
osu_args.add_argument('--no-video', dest='with_video', action='store_false',
                      help='downloads maps without video (only for osu, not bloodcat)')

bloodcat_args = parser.add_argument_group(
    'bloodcat', 'bloodcat-related arguments')
bloodcat_args.add_argument('--bloodcat', dest='use_bloodcat',
                           action='store_true', help='enables downloading via bloodcat')
bloodcat_args.add_argument('--no-bloodcat', dest='use_bloodcat',
                           action='store_false', help='disables downloading via bloodcat')
parser.set_defaults(use_osu=None, use_bloodcat=None, with_video=None)


def cooldown(secs: float, queue: 'Queue[Tuple[str, str, Optional[Exception]]]') -> None:
    time.sleep(secs)
    queue.put(('timer', '', None))


class FriendlyError(Exception):
    pass


class Args:
    def __init__(self):
        self.use_osu = True
        self.use_bloodcat = True
        self.osu_username = ''
        self.osu_password = ''
        self.ids_file = ''
        self.out_dir = ''
        self.with_video = False
        self.max_errors_in_a_row = 5


class DownloadList:
    def __init__(self, osu_and_bloodcat: Set[str], osu_only: Set[str], bloodcat_only: Set[str]):
        self.osu_and_bloodcat = osu_and_bloodcat
        self.osu_only = osu_only
        self.bloodcat_only = bloodcat_only
        self.resumed = False

    def remove_already_downloaded(self, already_dled: Set[str]):
        self.osu_and_bloodcat -= already_dled
        self.osu_only -= already_dled
        self.bloodcat_only -= already_dled

    def next_for_osu(self) -> Optional[str]:
        if len(self.osu_only) > 0:
            return self.osu_only.pop()
        elif len(self.osu_and_bloodcat) > 0:
            return self.osu_and_bloodcat.pop()
        return None

    def next_for_bloodcat(self) -> Optional[str]:
        if len(self.bloodcat_only) > 0:
            return self.bloodcat_only.pop()
        elif len(self.osu_and_bloodcat) > 0:
            return self.osu_and_bloodcat.pop()
        return None

    def __len__(self) -> int:
        return len(self.osu_and_bloodcat) + len(self.osu_only) + len(self.bloodcat_only)

    def __isub__(self, other: Set[str]) -> 'DownloadList':
        self.osu_and_bloodcat -= other
        self.osu_only -= other
        self.bloodcat_only -= other
        return self


def main() -> int:
    try:
        return _main()
    except FriendlyError as e:
        print(e)
        return 1
    except Exception as e:
        print(f'Unexpected error. Please report this.')
        traceback.print_exc()
        return 1


def _main() -> int:
    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parse_args()
    if args.use_osu and (args.osu_username == '' or args.osu_password == ''):
        raise FriendlyError(messages.missing_login_data)
    if not args.use_osu and not args.use_bloodcat:
        raise FriendlyError(messages.no_download_sources)

    os.makedirs(args.out_dir, exist_ok=True)
    dl_list = read_ids(args.ids_file)
    dl_list -= scan_existing_sets(args.out_dir)

    if len(dl_list) == 0:
        print(messages.nothing_to_download)
        return 0

    osu_dl = new_osu_dl(args)
    bloodcat_dl = new_bloodcat_dl(args)

    if args.use_osu and args.use_bloodcat:
        print(messages.checking_bloodcat_availability)
        update_bloodcat_availability(dl_list, bloodcat_dl)
        write_resume_file(args.ids_file, dl_list)

    print('')
    print(messages.downloading_n_sets(len(dl_list)))
    return download(dl_list, args, osu_dl, bloodcat_dl)


def parse_args() -> Args:
    args = parser.parse_args()

    cfg = configparser.ConfigParser(
        allow_no_value=True, empty_lines_in_values=False)
    cfg.read(args.cfg_file)

    result = Args()
    result.ids_file = str(args.ids_file)
    result.out_dir = str(args.out_dir)
    result.max_errors_in_a_row = args.max_errors_in_a_row
    result.use_osu = cfg.getboolean('osu', 'use', fallback=True)
    result.use_bloodcat = cfg.getboolean('bloodcat', 'use', fallback=True)
    result.osu_username = cfg.get('osu', 'username', fallback='')
    result.osu_password = cfg.get('osu', 'password', fallback='')
    result.with_video = cfg.getboolean('osu', 'video', fallback=False)
    if args.use_osu is not None:
        result.use_osu = bool(args.use_osu)
    if args.use_bloodcat is not None:
        result.use_bloodcat = bool(args.use_bloodcat)
    if args.osu_username is not None:
        result.osu_username = str(args.osu_username)
    if args.osu_password is not None:
        result.osu_password = str(args.osu_password)
    if args.with_video is not None:
        result.with_video = bool(args.with_video)
    return result


def scan_existing_sets(dir: str) -> Set[str]:
    sets = {item.name.split()[0] for item in os.scandir(dir)}
    return {s for s in sets if s.isdigit()}


def read_ids(ids_file: str) -> DownloadList:
    if ids_file.lower().endswith('.resume'):
        return read_resume_file(ids_file)

    with open(ids_file) as f:
        ids = [line.strip() for line in f]
        return DownloadList(
            osu_and_bloodcat={id for id in ids if id != ''},
            osu_only=set(), bloodcat_only=set(),
        )


def read_resume_file(file: str) -> DownloadList:
    with open(file) as f:
        try:
            j = json.load(f)
            dl_list = DownloadList(
                osu_and_bloodcat=set(j['set_ids']),
                osu_only=set(j['osu_exc']),
                bloodcat_only=set(j['bloodcat_exc']),
            )
            dl_list.resumed = True
            return dl_list
        except:
            raise FriendlyError(messages.bad_resume_file(file))


def new_osu_dl(args: Args) -> osu.Downloader:
    if not args.use_osu:
        return osu.Downloader(False)

    dl = osu.Downloader(args.with_video)
    try:
        dl.login(args.osu_username, args.osu_password)
        return dl
    except osu.WrongCredentials:
        raise FriendlyError(messages.wrong_credentials)
    except (osu.LoginError, osu.ConnectionError) as e:
        raise FriendlyError(e)


def new_bloodcat_dl(_: Args) -> bloodcat.Downloader:
    return bloodcat.Downloader()


def update_bloodcat_availability(dl_list: DownloadList, bloodcat_dl: bloodcat.Downloader) -> None:
    if dl_list.resumed:
        return

    for i, set_id in enumerate(dl_list.osu_and_bloodcat):
        print(f'{i+1} / {len(dl_list.osu_and_bloodcat)}', end='\r')
        try:
            available = bloodcat_dl.check_availability(set_id)
            if not available:
                dl_list.osu_only.add(set_id)
        except (bloodcat.ConnectionError, bloodcat.SearchError) as e:
            print('')
            raise FriendlyError(e)

    print('')
    dl_list.osu_and_bloodcat -= dl_list.osu_only


def write_resume_file(ids_file: str, dl_list: DownloadList) -> None:
    if ids_file.lower().endswith('.resume'):
        return

    resume_file = ids_file + '.resume'
    with open(resume_file, 'w') as f:
        json.dump({
            'set_ids': list(dl_list.osu_and_bloodcat),
            'osu_exc': list(dl_list.osu_only),
            'bloodcat_exc': list(dl_list.bloodcat_only),
        }, f)

    print(messages.created_resume_file(ids_file, resume_file))


def download(dl_list: DownloadList, args: Args, osu_dl: osu.Downloader, bloodcat_dl: bloodcat.Downloader) -> int:
    osu_queue: 'Queue[str]' = Queue(maxsize=1)
    bloodcat_queue: 'Queue[str]' = Queue(maxsize=1)
    results_queue: 'Queue[Tuple[str, str, Optional[Exception]]]' = Queue()

    osu_proc = Process()
    bloodcat_proc = Process()
    osu_cooldown_proc = Process()

    osu_busy = False
    bloodcat_busy = False
    osu_errors_in_a_row = 0
    bloodcat_errors_in_a_row = 0

    missing_on_osu = dl_list.bloodcat_only.copy()
    missing_on_bloodcat = dl_list.osu_only.copy()

    def fill_queues():
        nonlocal osu_busy, bloodcat_busy
        if args.use_osu and not osu_busy:
            item = dl_list.next_for_osu()
            if item is not None:
                osu_busy = True
                osu_queue.put(item)
        if args.use_bloodcat and not bloodcat_busy:
            item = dl_list.next_for_bloodcat()
            if item is not None:
                bloodcat_busy = True
                bloodcat_queue.put(item)

    def cleanup():
        if args.use_osu:
            osu_queue.put('stop')
        if args.use_bloodcat:
            bloodcat_queue.put('stop')
        if osu_cooldown_proc.is_alive():
            osu_cooldown_proc.kill()

    total = len(dl_list)
    if args.use_osu:
        osu_proc = Process(target=osu_dl.download_mapsets, args=(
            'osu', args.out_dir, osu_queue, results_queue,
        ))
        osu_proc.start()
    if args.use_bloodcat:
        bloodcat_proc = Process(target=bloodcat_dl.download_mapsets, args=(
            'bloodcat', args.out_dir, bloodcat_queue, results_queue,
        ))
        bloodcat_proc.start()

    fill_queues()

    done = 0
    try:
        while done < total:
            worker, set_id, error = results_queue.get()
            if error is None:
                if worker == 'timer':
                    osu_busy = False
                    fill_queues()
                    continue

                done += 1
                print(f'[progress] {done} / {total}')

                if worker == 'osu':
                    osu_busy = False
                    osu_errors_in_a_row = 0
                elif worker == 'bloodcat':
                    bloodcat_busy = False
                    bloodcat_errors_in_a_row = 0

                fill_queues()
            elif worker == 'osu' and isinstance(error, osu.MapsetUnavailable):
                missing_on_osu.add(set_id)
                if not args.use_bloodcat or set_id in missing_on_bloodcat:
                    print('[info]', error)
                    total -= 1
                else:
                    dl_list.bloodcat_only.add(set_id)

                osu_busy = False
                fill_queues()
            elif worker == 'bloodcat' and isinstance(error, bloodcat.MapsetUnavailable):
                missing_on_bloodcat.add(set_id)
                if not args.use_osu or set_id in missing_on_osu:
                    print('[info]', error)
                    total -= 1
                else:
                    dl_list.osu_only.add(set_id)

                bloodcat_busy = False
                fill_queues()
            elif worker == 'osu' and isinstance(error, osu.QuotaExceeded):
                print(messages.download_limit_reached('five minutes'))
                if args.use_bloodcat and set_id not in missing_on_bloodcat:
                    dl_list.osu_and_bloodcat.add(set_id)
                else:
                    dl_list.osu_only.add(set_id)

                osu_cooldown_proc = Process(
                    target=cooldown, args=(60*5, results_queue))
                osu_cooldown_proc.start()
            elif worker == 'osu':  # and error is not None
                if osu_errors_in_a_row < args.max_errors_in_a_row:
                    osu_errors_in_a_row += 1
                    osu_queue.put(set_id)
                    continue

                print(f"[osu] Couldn't download mapset #{set_id}:\n{error}")
                cleanup()
                return 1
            elif worker == 'bloodcat':  # and error is not None
                if bloodcat_errors_in_a_row < args.max_errors_in_a_row:
                    bloodcat_errors_in_a_row += 1
                    bloodcat_queue.put(set_id)
                    continue

                print(
                    f"[bloodcat] Couldn't download mapset #{set_id}:\n{error}")
                cleanup()
                return 1
    except:
        if osu_proc.is_alive():
            osu_proc.kill()
        if bloodcat_proc.is_alive():
            bloodcat_proc.kill()
        if osu_cooldown_proc.is_alive():
            osu_cooldown_proc.kill()
        raise

    cleanup()
    return 0


if __name__ == "__main__":
    exit(main())

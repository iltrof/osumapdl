import argparse
import configparser
import json
from multiprocessing import Process, Queue
import os
import sys
import time
import traceback
from typing import Optional, Set, Tuple

import chimu
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
                      help='downloads maps with video whenever possible (only for osu, not chimu)')
osu_args.add_argument('--no-video', dest='with_video', action='store_false',
                      help='downloads maps without video (only for osu, not chimu)')

chimu_args = parser.add_argument_group(
    'chimu', 'chimu-related arguments')
chimu_args.add_argument('--chimu', dest='use_chimu',
                           action='store_true', help='enables downloading via chimu')
chimu_args.add_argument('--no-chimu', dest='use_chimu',
                           action='store_false', help='disables downloading via chimu')
parser.set_defaults(use_osu=None, use_chimu=None, with_video=None)


def cooldown(secs: float, queue: 'Queue[Tuple[str, str, Optional[Exception]]]') -> None:
    time.sleep(secs)
    queue.put(('timer', '', None))


class FriendlyError(Exception):
    pass


class Args:
    def __init__(self):
        self.use_osu = True
        self.use_chimu = True
        self.osu_username = ''
        self.osu_password = ''
        self.ids_file = ''
        self.out_dir = ''
        self.with_video = False
        self.max_errors_in_a_row = 5


class DownloadList:
    def __init__(self, osu_and_chimu: Set[str], osu_only: Set[str], chimu_only: Set[str]):
        self.osu_and_chimu = osu_and_chimu
        self.osu_only = osu_only
        self.chimu_only = chimu_only
        self.resumed = False

    def remove_already_downloaded(self, already_dled: Set[str]):
        self.osu_and_chimu -= already_dled
        self.osu_only -= already_dled
        self.chimu_only -= already_dled

    def next_for_osu(self) -> Optional[str]:
        if len(self.osu_only) > 0:
            return self.osu_only.pop()
        elif len(self.osu_and_chimu) > 0:
            return self.osu_and_chimu.pop()
        return None

    def next_for_chimu(self) -> Optional[str]:
        if len(self.chimu_only) > 0:
            return self.chimu_only.pop()
        elif len(self.osu_and_chimu) > 0:
            return self.osu_and_chimu.pop()
        return None

    def __len__(self) -> int:
        return len(self.osu_and_chimu) + len(self.osu_only) + len(self.chimu_only)

    def __isub__(self, other: Set[str]) -> 'DownloadList':
        self.osu_and_chimu -= other
        self.osu_only -= other
        self.chimu_only -= other
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
    if not args.use_osu and not args.use_chimu:
        raise FriendlyError(messages.no_download_sources)

    os.makedirs(args.out_dir, exist_ok=True)
    dl_list = read_ids(args.ids_file)
    dl_list -= scan_existing_sets(args.out_dir)

    if len(dl_list) == 0:
        print(messages.nothing_to_download)
        return 0

    osu_dl = new_osu_dl(args)
    chimu_dl = new_chimu_dl(args)

    if args.use_osu and args.use_chimu:
        print(messages.checking_chimu_availability)
        update_chimu_availability(dl_list, chimu_dl)
        write_resume_file(args.ids_file, dl_list)

    print('')
    print(messages.downloading_n_sets(len(dl_list)))
    return download(dl_list, args, osu_dl, chimu_dl)


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
    result.use_chimu = cfg.getboolean('chimu', 'use', fallback=True)
    result.osu_username = cfg.get('osu', 'username', fallback='')
    result.osu_password = cfg.get('osu', 'password', fallback='')
    result.with_video = cfg.getboolean('osu', 'video', fallback=False)
    if args.use_osu is not None:
        result.use_osu = bool(args.use_osu)
    if args.use_chimu is not None:
        result.use_chimu = bool(args.use_chimu)
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
            osu_and_chimu={id for id in ids if id != ''},
            osu_only=set(), chimu_only=set(),
        )


def read_resume_file(file: str) -> DownloadList:
    with open(file) as f:
        try:
            j = json.load(f)
            dl_list = DownloadList(
                osu_and_chimu=set(j['set_ids']),
                osu_only=set(j['osu_exc']),
                chimu_only=set(j['chimu_exc']),
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


def new_chimu_dl(_: Args) -> chimu.Downloader:
    return chimu.Downloader()


def update_chimu_availability(dl_list: DownloadList, chimu_dl: chimu.Downloader) -> None:
    if dl_list.resumed:
        return

    for i, set_id in enumerate(dl_list.osu_and_chimu):
        print(f'{i+1} / {len(dl_list.osu_and_chimu)}', end='\r')
        try:
            available = chimu_dl.check_availability(set_id)
            if not available:
                dl_list.osu_only.add(set_id)
        except (chimu.ConnectionError, chimu.SearchError) as e:
            print('')
            raise FriendlyError(e)

    print('')
    dl_list.osu_and_chimu -= dl_list.osu_only


def write_resume_file(ids_file: str, dl_list: DownloadList) -> None:
    if ids_file.lower().endswith('.resume'):
        return

    resume_file = ids_file + '.resume'
    with open(resume_file, 'w') as f:
        json.dump({
            'set_ids': list(dl_list.osu_and_chimu),
            'osu_exc': list(dl_list.osu_only),
            'chimu_exc': list(dl_list.chimu_only),
        }, f)

    print(messages.created_resume_file(ids_file, resume_file))


def download(dl_list: DownloadList, args: Args, osu_dl: osu.Downloader, chimu_dl: chimu.Downloader) -> int:
    osu_queue: 'Queue[str]' = Queue(maxsize=1)
    chimu_queue: 'Queue[str]' = Queue(maxsize=1)
    results_queue: 'Queue[Tuple[str, str, Optional[Exception]]]' = Queue()

    osu_proc = Process()
    chimu_proc = Process()
    osu_cooldown_proc = Process()

    osu_busy = False
    chimu_busy = False
    osu_errors_in_a_row = 0
    chimu_errors_in_a_row = 0

    missing_on_osu = dl_list.chimu_only.copy()
    missing_on_chimu = dl_list.osu_only.copy()

    def fill_queues():
        nonlocal osu_busy, chimu_busy
        if args.use_osu and not osu_busy:
            item = dl_list.next_for_osu()
            if item is not None:
                osu_busy = True
                osu_queue.put(item)
        if args.use_chimu and not chimu_busy:
            item = dl_list.next_for_chimu()
            if item is not None:
                chimu_busy = True
                chimu_queue.put(item)

    def cleanup():
        if args.use_osu:
            osu_queue.put('stop')
        if args.use_chimu:
            chimu_queue.put('stop')
        if osu_cooldown_proc.is_alive():
            osu_cooldown_proc.kill()

    total = len(dl_list)
    if args.use_osu:
        osu_proc = Process(target=osu_dl.download_mapsets, args=(
            'osu', args.out_dir, osu_queue, results_queue,
        ))
        osu_proc.start()
    if args.use_chimu:
        chimu_proc = Process(target=chimu_dl.download_mapsets, args=(
            'chimu', args.out_dir, chimu_queue, results_queue,
        ))
        chimu_proc.start()

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
                elif worker == 'chimu':
                    chimu_busy = False
                    chimu_errors_in_a_row = 0

                fill_queues()
            elif worker == 'osu' and isinstance(error, osu.MapsetUnavailable):
                missing_on_osu.add(set_id)
                if not args.use_chimu or set_id in missing_on_chimu:
                    print('[info]', error)
                    total -= 1
                else:
                    dl_list.chimu_only.add(set_id)

                osu_busy = False
                fill_queues()
            elif worker == 'chimu' and isinstance(error, chimu.MapsetUnavailable):
                missing_on_chimu.add(set_id)
                if not args.use_osu or set_id in missing_on_osu:
                    print('[info]', error)
                    total -= 1
                else:
                    dl_list.osu_only.add(set_id)

                chimu_busy = False
                fill_queues()
            elif worker == 'osu' and isinstance(error, osu.QuotaExceeded):
                print(messages.download_limit_reached('five minutes'))
                if args.use_chimu and set_id not in missing_on_chimu:
                    dl_list.osu_and_chimu.add(set_id)
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
            elif worker == 'chimu':  # and error is not None
                if chimu_errors_in_a_row < args.max_errors_in_a_row:
                    chimu_errors_in_a_row += 1
                    chimu_queue.put(set_id)
                    continue

                print(
                    f"[chimu] Couldn't download mapset #{set_id}:\n{error}")
                cleanup()
                return 1
    except:
        if osu_proc.is_alive():
            osu_proc.kill()
        if chimu_proc.is_alive():
            chimu_proc.kill()
        if osu_cooldown_proc.is_alive():
            osu_cooldown_proc.kill()
        raise

    cleanup()
    return 0


if __name__ == "__main__":
    exit(main())

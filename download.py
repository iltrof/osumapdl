import argparse
import configparser
import json
from multiprocessing import Process, Queue
import os
import sys
import time
import traceback
from typing import Dict, List, Optional, Set, Tuple

import bloodcat
import osu


class State:
    def __init__(self, set_id: str) -> None:
        self.set_id = set_id
        self.downloaded: bool = False
        self.not_on_osu: bool = False
        self.not_on_bloodcat: bool = False


def cooldown(secs: float, queue: 'Queue[Tuple[str, str, Optional[Exception]]]') -> None:
    time.sleep(secs)
    queue.put(('timer', '', None))


def main() -> int:
    parser = argparse.ArgumentParser(usage='%(prog)s [options] ids_file')
    parser.add_argument('--cfg', dest='cfg_file', metavar='cfg-file',
                        action='store', help='config file to use', default='dlconfig.ini')
    parser.add_argument('ids_file', action='store',
                        help='file with IDs of mapsets you want downloaded')
    parser.add_argument('-o', '--out', action='store', dest='out_dir',
                        default='downloads', help='folder to download files into')

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

    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()

    cfg = configparser.ConfigParser(
        allow_no_value=True, empty_lines_in_values=False)
    cfg.read(args.cfg_file)

    use_osu = (cfg.getboolean('osu', 'use', fallback=False)
               if args.use_osu is None else args.use_osu)
    use_bloodcat = (cfg.getboolean('bloodcat', 'use', fallback=True)
                    if args.use_bloodcat is None else args.use_bloodcat)
    osu_username = (cfg.get('osu', 'username', fallback='')
                    if args.osu_username is None else args.osu_username)
    osu_password = (cfg.get('osu', 'password', fallback='')
                    if args.osu_password is None else args.osu_password)
    with_video = (cfg.getboolean('osu', 'video', fallback=False)
                  if args.with_video is None else args.with_video)

    if use_osu and (osu_username == '' or osu_password == ''):
        print('If you want to download from osu,\n'
              'please provide both your username and password.\n'
              'You can do that in the config file (dlconfig.ini).')
        return 1

    if not use_osu and not use_bloodcat:
        print("You've disabled both downloads via osu and via bloodcat.\n"
              'If you actually want to download something, please enable\n'
              'at least one of the options.')
        return 1

    osu_dl = osu.Downloader(with_video)
    bloodcat_dl = bloodcat.Downloader()
    if use_osu:
        try:
            osu_dl.login(osu_username, osu_password)
        except osu.WrongCredentials:
            print('Your osu username/password seems to be wrong.\n'
                  "Check that you've entered them correctly and try again.")
            return 1
        except (osu.LoginError, osu.ConnectionError) as e:
            print(e.args[0] + '\n'
                  'Check that the osu website even works and try again.')
            return 1

    os.makedirs(args.out_dir, exist_ok=True)

    already_downloaded: Set[str] = set()
    for item in os.scandir(args.out_dir):
        try:
            setid = int(item.name.split()[0])
            already_downloaded.add(str(setid))
        except:
            pass

    resume = args.ids_file.lower().endswith('.resume')

    states: Dict[str, State] = {}
    if not resume:
        with open(args.ids_file) as f:
            for line in f:
                id = line.strip()
                if id != '' and id not in already_downloaded:
                    states[id] = State(id)
        if len(states) == 0:
            print('No maps to download.')
            return 0

    osu_exclusive: List[str] = []
    bloodcat_exclusive: List[str] = []
    if not resume and use_osu and use_bloodcat:
        print('Checking which maps are unavailable on bloodcat...')
        try:
            for i, set_id in enumerate(states.keys()):
                print(f'{i+1} / {len(states)}', end='\r')
                available = bloodcat_dl.check_availability(set_id)
                if not available:
                    states[set_id].not_on_bloodcat = True
                    osu_exclusive.append(set_id)
            print('')
        except bloodcat.ConnectionError as e:
            print(f'\n{e.args[0]}\n'
                  'Check if the website even works and try again.')
            return 1
        except bloodcat.SearchError as e:
            print(f'\n{e.args[0]}')
            return 1

    set_ids = [
        k for k in states if k not in osu_exclusive and k not in bloodcat_exclusive]

    if resume:
        with open(args.ids_file) as f:
            j = json.load(f)
            set_ids = [id for id in j['set_ids']
                       if id not in already_downloaded]
            if use_osu:
                osu_exclusive = [id for id in j['osu_exc']
                                 if id not in already_downloaded]
            if use_bloodcat:
                bloodcat_exclusive = [id for id in j['bloodcat_exc']
                                      if id not in already_downloaded]

            for id in set_ids + osu_exclusive + bloodcat_exclusive:
                states[id] = State(id)
            if len(states) == 0:
                print('No maps to download.')
                return 0

    if not resume:
        with open(args.ids_file + '.resume', 'w') as f:
            json.dump({'set_ids': set_ids, 'osu_exc': osu_exclusive,
                       'bloodcat_exc': bloodcat_exclusive}, f)
            print(f'Created {args.ids_file}.resume file.\n'
                  f'If the script breaks, run it with {args.ids_file}.resume\n'
                  f'instead of just {args.ids_file} to avoid long preparations.')

    print(f'Downloading {len(states)} '
          f'map{"" if len(states) == 1 else "s"}...')

    osu_queue: 'Queue[str]' = Queue(maxsize=1)
    bloodcat_queue: 'Queue[str]' = Queue(maxsize=1)
    results_queue: 'Queue[Tuple[str, str, Optional[Exception]]]' = Queue()

    osu_proc = Process()
    bloodcat_proc = Process()
    timer_proc = Process()

    osu_active = False
    bloodcat_active = False

    osu_errors_in_a_row = 0
    bloodcat_errors_in_a_row = 0

    total = len(states)
    if use_osu:
        osu_proc = Process(target=osu_dl.download_mapsets, args=(
            'osu', args.out_dir, osu_queue, results_queue))
        osu_proc.start()
        if len(osu_exclusive) > 0:
            osu_queue.put(osu_exclusive.pop())
        else:
            osu_queue.put(set_ids.pop())
        osu_active = True

    if use_bloodcat:
        bloodcat_proc = Process(target=bloodcat_dl.download_mapsets, args=(
            'bloodcat', args.out_dir, bloodcat_queue, results_queue))
        bloodcat_proc.start()
        if len(bloodcat_exclusive) > 0:
            bloodcat_queue.put(bloodcat_exclusive.pop())
            bloodcat_active = True
        elif len(set_ids) > 0:
            bloodcat_queue.put(set_ids.pop())
            bloodcat_active = True

    done = 0
    while done < total:
        worker, set_id, error = results_queue.get()
        if (worker == 'osu' or worker == 'bloodcat') and error is None:
            done += 1
            print(f'[progress] {done} / {total}')
            states[set_id].downloaded = True

            if worker == 'osu':
                osu_active = False
                osu_errors_in_a_row = 0
                if len(osu_exclusive) > 0:
                    osu_queue.put(osu_exclusive.pop())
                    osu_active = True
                elif len(set_ids) > 0:
                    osu_queue.put(set_ids.pop())
                    osu_active = True
            elif worker == 'bloodcat':
                bloodcat_active = False
                bloodcat_errors_in_a_row = 0
                if len(bloodcat_exclusive) > 0:
                    bloodcat_queue.put(bloodcat_exclusive.pop())
                    bloodcat_active = True
                elif len(set_ids) > 0:
                    bloodcat_queue.put(set_ids.pop())
                    bloodcat_active = True
            continue

        if worker == 'osu' and isinstance(error, osu.MapsetUnavailable):
            states[set_id].not_on_osu = True
            if not use_bloodcat or states[set_id].not_on_bloodcat:
                print('[info]', error.args[0])
                total -= 1
            else:
                bloodcat_exclusive.append(set_id)

            osu_active = False
            if len(osu_exclusive) > 0:
                osu_queue.put(osu_exclusive.pop())
                osu_active = True
            elif len(set_ids) > 0:
                osu_queue.put(set_ids.pop())
                osu_active = True
        elif worker == 'osu' and isinstance(error, osu.QuotaExceeded):
            print("[info] You've reached the hourly download limit on osu,\n"
                  "so it's now rejecting download requests.\n"
                  'The script will try again in five minutes.')
            osu_active = False
            set_ids.append(set_id)
            timer_proc = Process(target=cooldown, args=(60*5, results_queue))
            timer_proc.start()
        elif worker == 'osu' and osu_errors_in_a_row <= 3:
            osu_errors_in_a_row += 1
            osu_queue.put(set_id)
        elif worker == 'osu':  # error is not None
            print(f"[osu] Couldn't download mapset #{set_id}:\n"
                  f"{error.args[0]}")
            osu_proc.kill()
            if bloodcat_proc.is_alive():
                bloodcat_proc.kill()
            if timer_proc.is_alive():
                timer_proc.kill()
            return 1
        elif worker == 'bloodcat' and isinstance(error, bloodcat.MapsetUnavailable):
            states[set_id].not_on_bloodcat = True
            if not use_osu or states[set_id].not_on_osu:
                print('[info]', error.args[0])
                total -= 1
            else:
                osu_exclusive.append(set_id)

            if len(bloodcat_exclusive) > 0:
                bloodcat_queue.put(bloodcat_exclusive.pop())
            elif len(set_ids) > 0:
                bloodcat_queue.put(set_ids.pop())
        elif worker == 'bloodcat' and bloodcat_errors_in_a_row <= 3:
            bloodcat_errors_in_a_row += 1
            bloodcat_queue.put(set_id)
        elif worker == 'bloodcat':  # error is not None
            print(f"[bloodcat] Couldn't download mapset #{set_id}:\n"
                  f"{error.args[0]}")
            bloodcat_proc.kill()
            if osu_proc.is_alive():
                osu_proc.kill()
            if timer_proc.is_alive():
                timer_proc.kill()
            return 1
        elif worker == 'timer':
            if len(osu_exclusive) > 0:
                osu_queue.put(osu_exclusive.pop())
            elif len(set_ids) > 0:
                osu_queue.put(set_ids.pop())

    if osu_proc.is_alive():
        if osu_active:
            results_queue.get()
        osu_proc.kill()
    if bloodcat_proc.is_alive():
        if bloodcat_active:
            results_queue.get()
        bloodcat_proc.kill()
    if timer_proc.is_alive():
        timer_proc.kill()
    return 0


if __name__ == "__main__":
    try:
        exit(main())
    except Exception as e:
        print('Unexpected error, please report this.')
        traceback.print_exc()
        exit(1)

missing_login_data = '''\
If you want to download from osu!,
please provide both your username and your password.
You can do that in the config file (dlconfig.ini).'''

no_download_sources = '''\
You've disabled both downloads via osu! and via chimu.
If you want to actually download anything, please
enable at least one of the options.'''

wrong_credentials = '''\
Your osu! username/password seems to be wrong.
Please check that you've entered them correctly.'''

nothing_to_download = '''\
Everything's already downloaded.'''


def bad_resume_file(path: str) -> str:
    return f'''\
The given resume file ({path}) seems to be corrupted.
Please give me a list of mapset IDs to download again.'''


def created_resume_file(ids_file: str, resume_file: str) -> str:
    return f'''\
[info] Created resume file: {resume_file}.
If the script breaks, run it with {resume_file}
instead of just {ids_file} to avoid long preparations.'''


checking_chimu_availability = '''\
[info] Checking which mapsets are unavailable on chimu...'''


def downloading_n_sets(n: int) -> str:
    plural = '' if n == 1 else 's'
    return f'[info] Downloading {n} mapset{plural}...'


def download_limit_reached(cooldown_time: str) -> str:
    return f'''\
[info] You've reached the hourly download limit on osu!,
so it's rejecting download requests for the moment.
The script will try osu! again in {cooldown_time}.'''

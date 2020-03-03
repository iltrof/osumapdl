# osu! map downloader

A python script to bulk download maps. Though, if
possible, you should prefer literally any other way of
downloading large amounts of maps, such as map packs.

Supports downloading both from the official osu! website,
as well as bloodcat.

## Installation

Go to
[releases](https://github.com/iltrof/osumapdl/releases),
grab the source code and extract it somewhere.

Prerequisites:

1. [Python](https://www.python.org/downloads/) 3.6+
   (`python --version` to check).
1. `pip install requests`.

## Usage

First, open `dlconfig.ini` and write your osu! username
and password into the corresponding fields. This is
required if you want to download via osu! servers (if you
don't want to or can't, set `osu = no` instead.)

By default mapsets are downloaded without video (at least
from the osu! website), but you can change that by
setting `video = yes` in `dlconfig.ini`.

Second, create a file with the list of mapsets you want
to download. The mapsets should be specified by their ID
(for instance, the `39804` in
https://osu.ppy.sh/beatmapsets/39804#osu/129891 is the
ID). One ID per line. As an example, this file will
download you freedom dive, blue zenith and uta:

```
39804
292301
410162
```

Also check out the `util` folder for scripts to help you
create such lists of mapset IDs.

Let's say you called your file `mapsets.txt` and put it
in the same location as the script. Then you just have to run:

```bash
python download.py mapsets.txt
```

The mapsets will be saved into a `downloads` folder in
the same location, though you can change the destination
with:

```bash
python download.py mapsets.txt -o "whatever-new-folder"
```

If you're having repeated problems with bloodcat, you can try raising the number of errors in a row after which the script will die. This is done via the `--max-errors` option:

```bash
python download.py mapsets.txt --max-errors 10
```

## When things break

The script, unfortunately, isn't fail-proof. If something
breaks, just try again, but if the error persists,
[open an
issue](https://github.com/iltrof/osumapdl/issues).

The script will also avoid downloading mapsets that have
already been downloaded to the best of its ability.

**Important** if you download both with osu! and bloodcat:
There is a slow-ish preparation phase where the script
checks which maps are not available on bloodcat. Once
that preparation phase is over, the script creates a
`.resume` file. For example, if your list of maps was
called `mapsets.txt`, the script will create
`mapsets.txt.resume`. When restarting, you should use
`mapsets.txt.resume` instead of just `mapsets.txt` to
avoid that long preparation phase.

## Configuration

Configuration is done via the config file
(`dlconfig.ini`). All of the settings are described in
the file itself. Alternatively, you can provide the same
settings via command-line flags (run `python download.py --help` for a list).

Besides the options described above under _Usage_, you
have the ability to enable/disable osu!/bloodcat, either
in the config file or by passing
`--osu`/`--no-osu`/`--bloodcat`/`--no-bloodcat` to the
script.

Flags provided via the command line, of course, take
precedence over the config file.

## What happens to your login data

Obviously, you shouldn't enter your passwords into things
you don't trust. Unfortunately, osu! requires you to be
logged in to download maps from it, so you'll have to
either look through the code or just trust the script.
Alternatively, disable osu! downloads and use bloodcat
instead; it's not bad either.

Your username & password are sent to
https://osu.ppy.sh/session, which is the same thing the
browser does when you log in to osu!. osu! sends back a
cookie to uniquely identify you, which is then used in
every request to download a map.

Neither the username, nor the password, nor that unique
cookie are sent anywhere other than osu.ppy.sh. The part
of the script that's responsible for osu! downloads is
also completely separate from the bloodcat downloads.

In other words, the script is equivalent to you going
into private mode, logging into osu!, downloading some
maps and closing the browser window.

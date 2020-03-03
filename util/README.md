Utility scripts to produce lists of mapset IDs.

## from-links.py

Extracts links to beatmaps/beatmap sets from a file and
creates a list of mapset IDs.

### Usage

```bash
python from-links.py input-file output-file
```

### Example

Given an input file such as:

```
https://osu.ppy.sh/b/75, https://osu.ppy.sh/s/3
https://osu.ppy.sh/beatmaps/129891 whatever junk text inbetween
http://osu.ppy.sh/beatmapsets/292301
```

This will be the output:

```
3
292301
1
39804
```

## user-played.py

Collects all of the mapsets a user has ever played.
("All" refers to all mapsets with a leaderboard.)

### Usage

By username:

```bash
python user-played.py chocomint
```

Or by user ID:

```bash
python user-played.py 124493
```

By default saves to `user + .txt`, but you can provide
the output file as an extra argument, e.g.:

```bash
python user-played.py chocomint cool-maps.txt
```

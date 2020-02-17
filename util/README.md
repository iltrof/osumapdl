Utility scripts to produce lists of mapset IDs.

## from-links.py

Extracts links to beatmaps/beatmap sets from a file and creates a list of mapset IDs.

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

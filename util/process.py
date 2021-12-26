import codecs
import json
import sys
import csv
import re

names = ['chocomint', 'nathan on osu', 'cookiezi', 'shigetora']
user_id = 124493

if len(sys.argv) != 3:
	print(f'Usage: python process.py input-file output-file')
	exit(1)
	
input_file = sys.argv[1]
output_file = sys.argv[2]

with codecs.open(input_file, 'r', 'utf-8') as f:
	j = json.load(f)

map_url_re = r'osu\.ppy\.sh/(?:b(?:eatmaps)?|beatmapsets/\d+#osu)/(\d+)'	
wr = csv.writer(codecs.open(output_file, 'w', 'utf-8'))
for (id, post) in j.items():
	if not any([n in post['title'].lower() for n in names]):
		continue
		
	url = f'https://reddit.com/{id}'
	title = post['title']
		
	if 'osubot' in post:
		if str(user_id) not in post['osubot']:
			continue
		
		map = re.search(map_url_re, post['osubot'])
		if map is None:
			wr.writerow([url, title])
		else:
			wr.writerow([url, title, f'https://osu.ppy.sh/beatmaps/{map[1]}'])
	else:
		wr.writerow([url, title])

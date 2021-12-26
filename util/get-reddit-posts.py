import codecs
import json
import requests
import time
import sys

names = ['chocomint', 'nathan on osu', 'cookiezi', 'shigetora']
accs = [f'{x}' for x in range(80, 101)] + ['SS']

if len(sys.argv) != 2:
	print(f'Usage: python get-reddit-posts.py output-file')
	exit(1)
	
output_file = sys.argv[1]

def get_all(query):
	posts = []
	after = ''
	while after is not None:
		r = requests.get(f'https://www.reddit.com/r/osugame/search/.json?q={query}&limit=100&after={after}', headers = {'User-Agent': 'osugame'})
		if not r.ok:
			print(f'Failed to search "{query}": {r.reason}. Retrying...')
			time.sleep(1)
			continue
			
		j = r.json()
		posts += j['data']['children']
		after = j['data']['after']
		time.sleep(0.5)
	
	return posts
	
posts = {}
size = 0
for n in names:
	for acc in accs:
		query = f'{n} {acc}'
		r = get_all(query)
		for item in r:
			if item['data']['subreddit'] == 'osugame':
				posts[item['data']['id']] = item['data']
		print(f'Found {len(posts) - size} results for {query}')
		size = len(posts)
		
print(f'{size} posts total')
print(f'Getting osu-bot comments...')

progress = 0
for (id, post) in posts.items():
	while True:
		r = requests.get(f'https://www.reddit.com/r/osugame/comments/{id}/.json', headers = {'User-Agent': 'osugame'})	
		if r.ok:
			break
			
		print(f'Failed to get comments for post {id}: {r.reason}. Retrying...')
		time.sleep(1)
	
	comments = r.json()
	osubot = [i['data']['body'] for i in comments[1]['data']['children'] if i['kind'] != 'more' and i['data']['author'] == 'osu-bot']
	if len(osubot) > 0:
		posts[id]['osubot'] = osubot[0]
		
	progress += 1
	print(f'{progress}/{size}')
	time.sleep(1)

with codecs.open(output_file, 'w', 'utf-8') as f:
	json.dump(posts, f)

#!/usr/bin/env python3
import requests
import time
from datetime import datetime, timezone, timedelta

headers = {'User-Agent': 'Mozilla/5.0'}
cutoff = datetime.now(timezone.utc) - timedelta(hours=72)

for subreddit in ['die_linke', 'finanzen']:
    print(f"\n{'='*60}")
    print(f"Testing r/{subreddit} - Last 72 hours")
    print(f"Cutoff: {cutoff}")
    print(f"{'='*60}")

    total = 0
    after = None

    for page in range(1, 6):
        url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=100"
        if after:
            url += f"&after={after}"

        time.sleep(2)
        data = requests.get(url, headers=headers, timeout=30).json()
        children = data['data']['children']
        after = data['data'].get('after')

        page_count = 0
        oldest = None
        newest = None

        for item in children:
            if item['kind'] != 't3':
                continue

            post_time = datetime.fromtimestamp(item['data']['created_utc'], tz=timezone.utc)

            if oldest is None or post_time < oldest:
                oldest = post_time
            if newest is None or post_time > newest:
                newest = post_time

            if post_time >= cutoff:
                page_count += 1
                total += 1
            else:
                print(f"  Page {page}: {page_count} posts within 72h (newest: {newest}, oldest: {oldest})")
                print(f"  STOPPED: Found post from {post_time} (older than {cutoff})")
                print(f"\nTOTAL for r/{subreddit}: {total} posts in last 72 hours")
                break
        else:
            print(f"  Page {page}: {page_count} posts within 72h (newest: {newest}, oldest: {oldest})")
            if not after:
                print(f"\nTOTAL for r/{subreddit}: {total} posts in last 72 hours (no more pages)")
                break
            continue
        break

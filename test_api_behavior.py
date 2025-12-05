#!/usr/bin/env python3
"""Test to see what Reddit API is actually returning"""
import requests
import time
from datetime import datetime, timezone

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

subreddit = 'finanzen'
print(f"Testing r/{subreddit} pagination\n{'='*60}")

after = None
for page in range(1, 4):
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=100"
    if after:
        url += f"&after={after}"

    print(f"\nPage {page}")
    print(f"URL: {url}")

    time.sleep(2)
    response = requests.get(url, headers=headers, timeout=30)
    data = response.json()

    children = data['data']['children']
    new_after = data['data'].get('after')

    posts = [item['data'] for item in children if item['kind'] == 't3']
    post_ids = [p['id'] for p in posts]

    print(f"Returned: {len(posts)} posts")
    print(f"After token: {after} -> {new_after}")
    print(f"First post ID: {post_ids[0] if post_ids else 'none'}")
    print(f"Last post ID: {post_ids[-1] if post_ids else 'none'}")

    if posts:
        first_time = datetime.fromtimestamp(posts[0]['created_utc'], tz=timezone.utc)
        last_time = datetime.fromtimestamp(posts[-1]['created_utc'], tz=timezone.utc)
        print(f"Time range: {first_time} to {last_time}")

    if new_after == after and after is not None:
        print("⚠️  PAGINATION TOKEN DIDN'T CHANGE!")
        break

    after = new_after

    if not after:
        print("No more pages")
        break

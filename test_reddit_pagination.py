#!/usr/bin/env python3
"""Test script to verify Reddit pagination behavior"""
import requests
import time
from datetime import datetime, timezone

def test_reddit_pagination(subreddit, max_pages=5):
    """Fetch a few pages and show timestamp distribution"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    after = None

    for page in range(1, max_pages + 1):
        url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=100"
        if after:
            url += f"&after={after}"

        print(f"\n{'='*60}")
        print(f"Page {page}")
        print(f"{'='*60}")

        time.sleep(2)
        response = requests.get(url, headers=headers, timeout=30)
        data = response.json()

        children = data['data']['children']
        after = data['data'].get('after')

        if not children:
            print("No more posts!")
            break

        # Get all post timestamps
        timestamps = []
        for item in children:
            if item['kind'] == 't3':
                created = item['data'].get('created_utc', 0)
                post_time = datetime.fromtimestamp(created, tz=timezone.utc)
                timestamps.append(post_time)

        if timestamps:
            print(f"Total posts: {len(timestamps)}")
            print(f"Newest: {max(timestamps)}")
            print(f"Oldest: {min(timestamps)}")
            print(f"Time span: {max(timestamps) - min(timestamps)}")

            # Check if sorted
            sorted_timestamps = sorted(timestamps, reverse=True)
            is_sorted = timestamps == sorted_timestamps
            print(f"Strictly sorted (newest first): {is_sorted}")

            if not is_sorted:
                print("\n⚠️  Posts are NOT in strict chronological order!")
                print("First 5 timestamps:")
                for i, ts in enumerate(timestamps[:5]):
                    print(f"  {i+1}. {ts}")

        if not after:
            print("\nNo 'after' token - end of results")
            break

if __name__ == "__main__":
    print("Testing r/finanzen pagination behavior...")
    test_reddit_pagination("finanzen", max_pages=5)

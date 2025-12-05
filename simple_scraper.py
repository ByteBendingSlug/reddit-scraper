#!/usr/bin/env python3
"""Simple Reddit Scraper - Uses Reddit's JSON API"""
import requests
import time
import logging
import os
import yaml
from datetime import datetime, timedelta, timezone
from database import Database


class SimpleRedditScraper:
    def __init__(self, db_path='reddit_data.db'):
        self.logger = logging.getLogger('RedditScraper')
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        self.rate_limit = 2  # seconds between requests
        self.timeout = 30
        self.max_retries = 3
        self.db = Database(db_path)

    def _make_request(self, url):
        """Make request with retry logic"""
        time.sleep(self.rate_limit)

        if not url.endswith('.json'):
            url += '.json'

        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, headers=self.headers, timeout=self.timeout)

                if response.status_code == 429:
                    wait = int(response.headers.get('Retry-After', 60))
                    self.logger.warning(f"Rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)

            except requests.exceptions.RequestException as e:
                self.logger.error(f"Request failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

        raise Exception(f"Failed after {self.max_retries} attempts")

    def scrape_subreddit(self, subreddit, hours=24, max_pages=None):
        """Scrape posts from subreddit within time range or page limit

        Args:
            subreddit: Subreddit name
            hours: Hours to look back (default: 24, None = no time limit)
            max_pages: Maximum pages to fetch (default: None = use time limit, or 50 as safety)
        """
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            self.logger.info(f"Scraping r/{subreddit} - last {hours} hours")
            self.logger.info(f"Cutoff time: {cutoff}")
        else:
            cutoff = None
            self.logger.info(f"Scraping r/{subreddit} - no time limit")

        if max_pages:
            self.logger.info(f"Max pages: {max_pages}")

        all_posts = []
        after = None
        page = 0
        found_old = False
        page_limit = max_pages if max_pages else 50  # Safety limit to prevent infinite loops

        while page < page_limit:
            page += 1
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=100"
            if after:
                url += f"&after={after}"

            try:
                data = self._make_request(url)
            except Exception as e:
                self.logger.error(f"Failed to fetch page {page}: {e}")
                break

            children = data['data']['children']
            new_after = data['data'].get('after')

            # self.logger.debug(f"  After token: {after} -> {new_after}")

            if not children:
                self.logger.info("No more posts available")
                break

            # Check if pagination token changed
            if new_after == after and after is not None:
                self.logger.warning(f"Pagination token didn't change! Possible Reddit API issue. Stopping.")
                break

            after = new_after

            page_posts = 0
            oldest_on_page = None
            newest_on_page = None

            for i, item in enumerate(children):
                if item['kind'] != 't3':
                    continue

                post_data = item['data']
                post_time = datetime.fromtimestamp(post_data.get('created_utc', 0), tz=timezone.utc)

                # Track oldest and newest on this page
                if oldest_on_page is None or post_time < oldest_on_page:
                    oldest_on_page = post_time
                if newest_on_page is None or post_time > newest_on_page:
                    newest_on_page = post_time

                # Check time cutoff if specified
                if cutoff and post_time < cutoff:
                    self.logger.info(f"Found post older than cutoff: {post_time} < {cutoff}")
                    found_old = True
                    break

                post = {
                    'id': post_data.get('id'),
                    'title': post_data.get('title'),
                    'author': post_data.get('author'),
                    'subreddit': post_data.get('subreddit'),
                    'selftext': post_data.get('selftext', ''),
                    'url': post_data.get('url'),
                    'score': post_data.get('score'),
                    'num_comments': post_data.get('num_comments'),
                    'created_utc': post_time,
                    'permalink': post_data.get('permalink'),
                    'upvote_ratio': post_data.get('upvote_ratio'),
                    'link_flair_text': post_data.get('link_flair_text'),
                }
                all_posts.append(post)
                self.db.save_post(post)
                page_posts += 1

            self.logger.info(f"Page {page}: Found {page_posts} new posts (total: {len(all_posts)} posts) - Range: {newest_on_page} to {oldest_on_page}")

            if not after:
                self.logger.info("No more pages available (no 'after' token)")
                break

            if found_old:
                self.logger.info("Reached cutoff time, stopping pagination")
                break

        if page >= page_limit:
            self.logger.warning(f"Reached max pages limit ({page_limit}), stopping")

        self.logger.info(f"Total: {len(all_posts)} posts")
        return all_posts

    def scrape_post(self, post_url):
        """Scrape a single post with comments"""
        self.logger.info(f"Scraping post: {post_url}")
        data = self._make_request(post_url)

        # Extract post
        post_listing = data[0]['data']['children'][0]['data']
        post = {
            'id': post_listing.get('id'),
            'title': post_listing.get('title'),
            'author': post_listing.get('author'),
            'subreddit': post_listing.get('subreddit'),
            'selftext': post_listing.get('selftext'),
            'url': post_listing.get('url'),
            'score': post_listing.get('score'),
            'num_comments': post_listing.get('num_comments'),
            'created_utc': datetime.fromtimestamp(post_listing.get('created_utc', 0), tz=timezone.utc),
            'upvote_ratio': post_listing.get('upvote_ratio'),
            'permalink': post_listing.get('permalink'),
            'link_flair_text': post_listing.get('link_flair_text'),
        }

        # Extract comments
        comments = self._extract_comments(data[1]['data']['children'])

        self.logger.info(f"Found {len(comments)} comments")

        # Save to database
        self.db.save_post(post)
        self.db.save_comments(post['id'], comments)

        return {'post': post, 'comments': comments}

    def _extract_comments(self, comments_data, depth=0):
        """Recursively extract comments"""
        comments = []
        for item in comments_data:
            if item['kind'] != 't1':
                continue

            data = item['data']
            comment = {
                'id': data.get('id'),
                'author': data.get('author'),
                'body': data.get('body'),
                'score': data.get('score'),
                'created_utc': datetime.fromtimestamp(data.get('created_utc', 0), tz=timezone.utc),
                'depth': depth,
                'parent_id': data.get('parent_id'),
            }
            comments.append(comment)

            # Get replies
            if 'replies' in data and data['replies'] and isinstance(data['replies'], dict):
                replies = data['replies']['data']['children']
                comments.extend(self._extract_comments(replies, depth + 1))

        return comments

    def scrape_multiple_subreddits(self, subreddits, hours=24, max_pages=None):
        """Scrape posts from multiple subreddits

        Args:
            subreddits: List of subreddit names
            hours: Hours to look back for each subreddit
            max_pages: Maximum pages per subreddit

        Returns:
            Total number of posts scraped
        """
        total_posts = 0
        for i, subreddit in enumerate(subreddits, 1):
            self.logger.info(f"[{i}/{len(subreddits)}] Scraping r/{subreddit}")
            try:
                posts = self.scrape_subreddit(subreddit, hours, max_pages)
                total_posts += len(posts)
            except Exception as e:
                self.logger.error(f"Failed to scrape r/{subreddit}: {e}")
                continue

        self.logger.info(f"Total: Scraped {total_posts} posts from {len(subreddits)} subreddits")
        return total_posts

    def scrape_comments_from_db(self, subreddit=None, without_comments=True, hours=None):
        """Scrape comments for posts already in database

        Args:
            subreddit: Only scrape posts from this subreddit
            without_comments: Only scrape posts that don't have comments yet (default: True)
            hours: Only scrape posts from last N hours

        Returns:
            Number of posts processed
        """
        posts = self.db.get_posts(subreddit=subreddit, without_comments=without_comments, hours=hours)

        if not posts:
            self.logger.info("No posts found matching criteria")
            return 0

        self.logger.info(f"Found {len(posts)} posts to scrape comments from")

        success = 0
        for i, post in enumerate(posts, 1):
            try:
                self.logger.info(f"[{i}/{len(posts)}] Scraping comments for: {post['title'][:50]}...")
                post_url = f"https://www.reddit.com{post['permalink']}"

                # Scrape the post (will update post and save comments)
                self.scrape_post(post_url)
                success += 1

            except Exception as e:
                self.logger.error(f"Failed to scrape post {post['id']}: {e}")
                continue

        self.logger.info(f"Successfully scraped comments from {success}/{len(posts)} posts")
        return success


def load_config():
    """Load config.yml if it exists"""
    if os.path.exists('config.yml'):
        try:
            with open('config.yml', 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logging.warning(f"Error reading config.yml: {e}")
    return {}


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Simple Reddit Scraper')
    parser.add_argument('--subreddit', '-s', help='Subreddit to scrape')
    parser.add_argument('--from-config', action='store_true',
                       help='Scrape all subreddits from config.yml')
    parser.add_argument('--hours', '-t', type=int, default=24, help='Hours to look back (default: 24, 0 = no time limit)')
    parser.add_argument('--max-pages', type=int, help='Maximum pages to fetch per subreddit (default: auto)')
    parser.add_argument('--post-url', '-p', help='Specific post URL to scrape')
    parser.add_argument('--scrape-comments', action='store_true',
                       help='Scrape comments for posts already in database')
    parser.add_argument('--all-posts', action='store_true',
                       help='With --scrape-comments: scrape ALL posts, not just those without comments')
    parser.add_argument('--stats', action='store_true', help='Show database stats')
    parser.add_argument('--db', help='Database path (default: from config.yml or ./reddit_data.db)')

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if '--debug' in args.__dict__.get('__extra', []) else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Get database path: CLI arg > config.yml > default
    config = load_config()
    db_path = args.db or config.get('database_path', 'reddit_data.db')

    try:
        scraper = SimpleRedditScraper(db_path=db_path)

        if args.stats:
            stats = scraper.db.get_stats()
            print(f"\nTotal posts: {stats['total_posts']}")
            print(f"Total comments: {stats['total_comments']}")
            print(f"Posts with comments: {stats['posts_with_comments']}")
            if stats['posts_by_subreddit']:
                print("\nPosts by subreddit:")
                for sub, count in stats['posts_by_subreddit'].items():
                    print(f"  r/{sub}: {count}")
            return 0

        if args.scrape_comments:
            # Scrape comments for posts in database
            without_comments = not args.all_posts  # Default: only posts without comments
            scraper.scrape_comments_from_db(
                subreddit=args.subreddit,
                without_comments=without_comments,
                hours=args.hours if args.hours != 24 else None  # None = all time
            )
            return 0

        if args.post_url:
            scraper.scrape_post(args.post_url)
            return 0

        if args.from_config:
            # Scrape all subreddits from config
            subreddits = config.get('subreddits', [])
            if not subreddits:
                logging.error("No subreddits found in config.yml")
                return 1
            hours = args.hours if args.hours > 0 else None
            scraper.scrape_multiple_subreddits(subreddits, hours, args.max_pages)
            return 0

        if args.subreddit:
            hours = args.hours if args.hours > 0 else None
            scraper.scrape_subreddit(args.subreddit, hours, args.max_pages)
            return 0

        parser.print_help()
        return 0

    except KeyboardInterrupt:
        logging.info("Interrupted")
        return 130
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

#!/usr/bin/env python3
"""Simple Reddit Scraper - Uses Reddit's HTML pages"""
import requests
import time
import logging
import os
import yaml
import re
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from database import Database


class SimpleRedditScraper:
    def __init__(self, db_path='reddit_data.db'):
        self.logger = logging.getLogger('RedditScraper')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
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
        seen_post_ids = set()  # Track post IDs to detect duplicates
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

            # Count items by type
            post_count = sum(1 for item in children if item['kind'] == 't3')
            self.logger.info(f"  API returned {len(children)} items ({post_count} posts), after: {after} -> {new_after}")

            if not children:
                self.logger.info("No more posts available")
                break

            # Check if pagination token changed
            if new_after == after and after is not None:
                self.logger.warning(f"Pagination token didn't change! Possible Reddit API issue. Stopping.")
                break

            after = new_after

            page_posts = 0
            duplicate_count = 0
            oldest_on_page = None
            newest_on_page = None

            for i, item in enumerate(children):
                if item['kind'] != 't3':
                    continue

                post_data = item['data']
                post_id = post_data.get('id')
                post_time = datetime.fromtimestamp(post_data.get('created_utc', 0), tz=timezone.utc)

                # Check for duplicate posts (indicates we're looping)
                if post_id in seen_post_ids:
                    duplicate_count += 1
                    continue

                seen_post_ids.add(post_id)

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

            if duplicate_count > 0:
                self.logger.warning(f"Page {page}: Found {duplicate_count} duplicate posts - stopping")
                break

            self.logger.info(f"Page {page}: Found {page_posts} new posts (total: {len(all_posts)} posts) - Range: {newest_on_page} to {oldest_on_page}")

            if page_posts == 0:
                self.logger.info("No new posts on this page, stopping")
                break

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

    def scrape_subreddit_html(self, subreddit, hours=24, max_pages=None):
        """Scrape posts from subreddit using HTML parsing (old.reddit.com)

        Args:
            subreddit: Subreddit name
            hours: Hours to look back (default: 24, None = no time limit)
            max_pages: Maximum pages to fetch (default: None = use time limit, or 50 as safety)
        """
        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            self.logger.info(f"Scraping r/{subreddit} (HTML) - last {hours} hours")
            self.logger.info(f"Cutoff time: {cutoff}")
        else:
            cutoff = None
            self.logger.info(f"Scraping r/{subreddit} (HTML) - no time limit")

        if max_pages:
            self.logger.info(f"Max pages: {max_pages}")

        all_posts = []
        seen_post_ids = set()
        after = None
        page = 0
        page_limit = max_pages if max_pages else 50
        pages_with_no_new_posts = 0  # Track consecutive pages with no new posts

        while page < page_limit:
            page += 1

            # Use old.reddit.com for easier HTML parsing
            url = f"https://old.reddit.com/r/{subreddit}/new"
            params = {'limit': 100}
            if after:
                params['after'] = after

            try:
                time.sleep(self.rate_limit)
                response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
                response.raise_for_status()
            except Exception as e:
                self.logger.error(f"Failed to fetch page {page}: {e}")
                break

            soup = BeautifulSoup(response.text, 'lxml')

            # Find all post containers
            posts_found = soup.find_all('div', class_='thing', attrs={'data-type': 'link'})

            if not posts_found:
                self.logger.info("No posts found on page")
                break

            self.logger.info(f"  HTML page returned {len(posts_found)} posts")

            page_posts = 0
            duplicate_count = 0
            skipped_old = 0
            oldest_on_page = None
            newest_on_page = None

            for post_elem in posts_found:
                try:
                    post_id = post_elem.get('data-fullname', '').replace('t3_', '')
                    if not post_id:
                        continue

                    # Check for duplicates
                    if post_id in seen_post_ids:
                        duplicate_count += 1
                        continue

                    seen_post_ids.add(post_id)

                    # Extract post data from HTML
                    timestamp_elem = post_elem.find('time')
                    if timestamp_elem and timestamp_elem.get('datetime'):
                        post_time = datetime.fromisoformat(timestamp_elem['datetime'].replace('Z', '+00:00'))
                    else:
                        # Fallback: try data-timestamp attribute
                        timestamp = post_elem.get('data-timestamp')
                        if timestamp:
                            post_time = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
                        else:
                            continue

                    # Track oldest and newest
                    if oldest_on_page is None or post_time < oldest_on_page:
                        oldest_on_page = post_time
                    if newest_on_page is None or post_time > newest_on_page:
                        newest_on_page = post_time

                    # Check time cutoff - but don't break, just skip this post
                    if cutoff and post_time < cutoff:
                        # Skip old posts but continue checking the rest
                        skipped_old += 1
                        continue

                    # Extract other fields
                    title_elem = post_elem.find('a', class_='title')
                    title = title_elem.text.strip() if title_elem else ''

                    author_elem = post_elem.find('a', class_='author')
                    author = author_elem.text if author_elem else '[deleted]'

                    score_elem = post_elem.find('div', class_='score unvoted')
                    if not score_elem:
                        score_elem = post_elem.find('div', class_='score')
                    score_text = score_elem.text if score_elem else '0'
                    try:
                        score = int(score_text.replace(',', ''))
                    except:
                        score = 0

                    comments_elem = post_elem.find('a', class_='comments')
                    num_comments = 0
                    if comments_elem:
                        comments_text = comments_elem.text
                        match = re.search(r'(\d+)', comments_text.replace(',', ''))
                        if match:
                            num_comments = int(match.group(1))

                    permalink = post_elem.get('data-permalink', '')
                    post_url = post_elem.get('data-url', '')

                    # Get selftext if available
                    expando = post_elem.find('div', class_='expando')
                    selftext = ''
                    if expando:
                        usertext = expando.find('div', class_='usertext-body')
                        if usertext:
                            selftext = usertext.get_text(strip=True)

                    post = {
                        'id': post_id,
                        'title': title,
                        'author': author,
                        'subreddit': subreddit,
                        'selftext': selftext,
                        'url': post_url,
                        'score': score,
                        'num_comments': num_comments,
                        'created_utc': post_time,
                        'permalink': permalink,
                        'upvote_ratio': None,  # Not available in HTML
                        'link_flair_text': None  # Could extract if needed
                    }

                    all_posts.append(post)
                    self.db.save_post(post)
                    page_posts += 1

                except Exception as e:
                    self.logger.warning(f"Failed to parse post: {e}")
                    continue

            if duplicate_count > 0:
                self.logger.warning(f"Page {page}: Found {duplicate_count} duplicate posts - stopping")
                break

            log_msg = f"Page {page}: Found {page_posts} new posts"
            if skipped_old > 0:
                log_msg += f" (skipped {skipped_old} old posts)"
            log_msg += f" (total: {len(all_posts)} posts) - Range: {newest_on_page} to {oldest_on_page}"
            self.logger.info(log_msg)

            if page_posts == 0:
                pages_with_no_new_posts += 1
                if pages_with_no_new_posts >= 2:
                    self.logger.info("No new posts found on last 2 pages, stopping")
                    break
            else:
                pages_with_no_new_posts = 0  # Reset counter if we found posts

            # Find next page button/link
            next_button = soup.find('span', class_='next-button')
            if next_button:
                next_link = next_button.find('a')
                if next_link and next_link.get('href'):
                    # Extract 'after' parameter from URL
                    import urllib.parse
                    parsed = urllib.parse.urlparse(next_link['href'])
                    query_params = urllib.parse.parse_qs(parsed.query)
                    after = query_params.get('after', [None])[0]
                else:
                    after = None
            else:
                after = None

            if not after:
                self.logger.info("No more pages available (no next button)")
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

    def scrape_multiple_subreddits(self, subreddits, hours=24, max_pages=None, use_html=True):
        """Scrape posts from multiple subreddits

        Args:
            subreddits: List of subreddit names
            hours: Hours to look back for each subreddit
            max_pages: Maximum pages per subreddit
            use_html: Use HTML scraping instead of JSON API (default: True)

        Returns:
            Total number of posts scraped
        """
        total_posts = 0
        for i, subreddit in enumerate(subreddits, 1):
            self.logger.info(f"[{i}/{len(subreddits)}] Scraping r/{subreddit}")
            try:
                if use_html:
                    posts = self.scrape_subreddit_html(subreddit, hours, max_pages)
                else:
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
    parser.add_argument('--use-json', action='store_true',
                       help='Use JSON API instead of HTML scraping (default: HTML)')
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
            use_html = not args.use_json  # HTML by default
            scraper.scrape_multiple_subreddits(subreddits, hours, args.max_pages, use_html)
            return 0

        if args.subreddit:
            hours = args.hours if args.hours > 0 else None
            if args.use_json:
                scraper.scrape_subreddit(args.subreddit, hours, args.max_pages)
            else:
                scraper.scrape_subreddit_html(args.subreddit, hours, args.max_pages)
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

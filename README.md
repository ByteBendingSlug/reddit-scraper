# Simple Reddit Scraper

A lightweight Reddit scraper that uses Reddit's public JSON API (no authentication required).

## What It Does

- Scrapes posts from subreddits with time filtering
- Scrapes individual posts with all comments
- Stores data in SQLite database
- Handles rate limiting and retries automatically

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.yml` to set your database path:

```yaml
# For Raspberry Pi with SSD:
database_path: /mnt/ssd/reddit-data/reddit.db

# Or use current directory (default):
database_path: reddit_data.db
```

## Usage

### 1. Scrape Posts (no comments)

Scrape subreddit posts from last 24 hours:
```bash
python simple_scraper.py --subreddit python
```

Scrape subreddit posts from last 6 hours:
```bash
python simple_scraper.py --subreddit python --hours 6
```

### 2. Scrape Comments for Posts in Database

Scrape comments for ALL posts without comments:
```bash
python simple_scraper.py --scrape-comments
```

Scrape comments for posts from specific subreddit:
```bash
python simple_scraper.py --scrape-comments --subreddit python
```

Scrape comments for recent posts only (last 24 hours):
```bash
python simple_scraper.py --scrape-comments --hours 24
```

Re-scrape comments for ALL posts (even those with comments):
```bash
python simple_scraper.py --scrape-comments --all-posts
```

### 3. Scrape Specific Post with Comments

```bash
python simple_scraper.py --post-url "https://www.reddit.com/r/python/comments/xyz/"
```

### 4. View Stats

```bash
python simple_scraper.py --stats
```

### 5. Override Config

```bash
python simple_scraper.py --subreddit python --db /path/to/custom.db
```

## Cron Job Setup (Raspberry Pi)

**Typical workflow:**
1. Daily cron: scrape new posts (fast, just metadata)
2. Weekly/monthly cron: scrape comments for those posts (slower)

### Setup:

1. Edit `config.yml` with your database path
2. Add to crontab:

```bash
crontab -e

# Scrape new posts daily at 2 AM
0 2 * * * cd /home/pi/reddit-scraper && /usr/bin/python3 simple_scraper.py --subreddit python --hours 24 >> /tmp/reddit.log 2>&1

# Scrape comments weekly on Sunday at 3 AM
0 3 * * 0 cd /home/pi/reddit-scraper && /usr/bin/python3 simple_scraper.py --scrape-comments --subreddit python >> /tmp/reddit.log 2>&1
```

**Or for multiple subreddits:**
```bash
# Scrape posts from multiple subreddits daily
0 2 * * * cd /home/pi/reddit-scraper && /usr/bin/python3 simple_scraper.py --subreddit python --hours 24 >> /tmp/reddit.log 2>&1
5 2 * * * cd /home/pi/reddit-scraper && /usr/bin/python3 simple_scraper.py --subreddit programming --hours 24 >> /tmp/reddit.log 2>&1
10 2 * * * cd /home/pi/reddit-scraper && /usr/bin/python3 simple_scraper.py --subreddit datascience --hours 24 >> /tmp/reddit.log 2>&1

# Scrape all comments weekly
0 3 * * 0 cd /home/pi/reddit-scraper && /usr/bin/python3 simple_scraper.py --scrape-comments >> /tmp/reddit.log 2>&1
```

## Database Schema

**posts table:** post_id, subreddit, author, title, selftext, url, score, num_comments, created_utc, upvote_ratio, permalink, link_flair_text

**comments table:** comment_id, post_id, parent_id, author, body, score, created_utc, depth

## Workflow Example

**Daily posts + weekly comments:**
```bash
# Day 1: Scrape posts
python simple_scraper.py --subreddit python --hours 24
# Result: 50 posts saved (no comments yet)

# Day 2: Scrape posts
python simple_scraper.py --subreddit python --hours 24
# Result: 45 new posts saved (total: 95 posts, no comments)

# Day 7: Scrape comments for all posts without comments
python simple_scraper.py --scrape-comments --subreddit python
# Result: Comments scraped for all 95 posts

# Day 8: Scrape posts
python simple_scraper.py --subreddit python --hours 24
# Result: 52 new posts (total: 147 posts, 95 with comments)

# Check stats
python simple_scraper.py --stats
# Shows: 147 total posts, 95 with comments
```

## How It Works

Reddit provides JSON data by appending `.json` to any URL. The scraper:
1. Fetches data from Reddit's JSON endpoints
2. Handles pagination and rate limiting
3. Filters posts by timestamp
4. Stores everything in SQLite
5. Can later scrape comments for saved posts

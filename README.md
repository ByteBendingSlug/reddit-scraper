# Simple Reddit Scraper

A lightweight Reddit scraper that parses HTML from old.reddit.com (no authentication required).

## What It Does

- Scrapes posts from subreddits with time filtering (HTML parsing - more reliable)
- Scrapes individual posts with all comments (JSON API for comments)
- Stores data in SQLite database
- Handles rate limiting and retries automatically
- Duplicate detection prevents infinite loops

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Edit `config.yml`:

```yaml
# Database path
database_path: reddit_data.db

# Subreddits to scrape
subreddits:
  - python
  - programming
  - datascience
  - MachineLearning

# For Raspberry Pi with SSD, use:
# database_path: /mnt/ssd/reddit-data/reddit.db
```

## Usage

### 1. Scrape Posts (no comments)

**Scrape ALL subreddits from config.yml:**
```bash
python simple_scraper.py --from-config
```

**Scrape ALL subreddits from last 6 hours:**
```bash
python simple_scraper.py --from-config --hours 6
```

**Scrape with page limit instead of time (max 5 pages per subreddit, ~500 posts):**
```bash
python simple_scraper.py --from-config --max-pages 5 --hours 0
```

**Or scrape single subreddit:**
```bash
python simple_scraper.py --subreddit python
python simple_scraper.py --subreddit python --hours 6
python simple_scraper.py --subreddit python --max-pages 3
```

**Use JSON API instead of HTML (less reliable):**
```bash
python simple_scraper.py --from-config --use-json
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

## Workflow Example

**Daily posts + weekly comments:**
```bash
# Day 1: Scrape posts from all subreddits in config.yml
python simple_scraper.py --from-config --hours 24
# Result: 150 posts saved from 4 subreddits (no comments yet)

# Day 2-6: Scrape posts daily
python simple_scraper.py --from-config --hours 24
# Result: ~150 new posts each day

# Day 7: Scrape comments for all posts without comments
python simple_scraper.py --scrape-comments
# Result: Comments scraped for ~900 posts from all subreddits

# Check stats
python simple_scraper.py --stats
# Shows: 900 total posts, 900 with comments, posts by subreddit
```

## How It Works

Reddit provides JSON data by appending `.json` to any URL. The scraper:
1. Fetches data from Reddit's JSON endpoints
2. Handles pagination and rate limiting
3. Filters posts by timestamp
4. Stores everything in SQLite
5. Can later scrape comments for saved posts

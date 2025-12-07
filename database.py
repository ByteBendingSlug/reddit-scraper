#!/usr/bin/env python3
"""Database operations for Reddit scraper"""
import sqlite3
import logging


class Database:
    def __init__(self, db_path='reddit_data.db'):
        self.db_path = db_path
        self.logger = logging.getLogger('Database')
        self._setup_database()

    def _setup_database(self):
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Posts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                subreddit TEXT NOT NULL,
                author TEXT,
                title TEXT NOT NULL,
                selftext TEXT,
                url TEXT,
                score INTEGER,
                num_comments INTEGER,
                created_utc TIMESTAMP,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                upvote_ratio REAL,
                permalink TEXT,
                link_flair_text TEXT
            )
        """)

        # Comments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                parent_id TEXT,
                author TEXT,
                body TEXT,
                score INTEGER,
                created_utc TIMESTAMP,
                depth INTEGER,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(post_id)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_utc)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)")

        conn.commit()
        conn.close()

    def save_post(self, post):
        """Save a post to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO posts
                (post_id, subreddit, author, title, selftext, url, score,
                 num_comments, created_utc, upvote_ratio, permalink, link_flair_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post['id'],
                post['subreddit'],
                post.get('author', '[deleted]'),
                post['title'],
                post.get('selftext', ''),
                post['url'],
                post.get('score', 0),
                post.get('num_comments', 0),
                post['created_utc'],
                post.get('upvote_ratio', 0),
                post['permalink'],
                post.get('link_flair_text', '')
            ))
            conn.commit()
            self.logger.debug(f"Saved post {post['id']}")
        except Exception as e:
            self.logger.error(f"Error saving post {post['id']}: {e}")
            conn.rollback()
        finally:
            conn.close()

    def save_comments(self, post_id, comments):
        """Save comments to the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        saved = 0
        for comment in comments:
            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO comments
                    (comment_id, post_id, parent_id, author, body, score,
                     created_utc, depth)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    comment['id'],
                    post_id,
                    comment.get('parent_id', ''),
                    comment.get('author', '[deleted]'),
                    comment.get('body', ''),
                    comment.get('score', 0),
                    comment['created_utc'],
                    comment.get('depth', 0)
                ))
                saved += 1
            except Exception as e:
                self.logger.error(f"Error saving comment {comment['id']}: {e}")

        conn.commit()
        conn.close()
        self.logger.info(f"Saved {saved} comments")

    def get_posts(self, subreddit=None, without_comments=False, hours=None):
        """Get posts from database with optional filters

        Args:
            subreddit: Filter by subreddit name
            without_comments: Only get posts that have no comments yet
            hours: Only get posts from last N hours

        Returns:
            List of post dictionaries with id and permalink
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT post_id, permalink, subreddit, title FROM posts"
        conditions = []
        params = []

        if subreddit:
            conditions.append("subreddit = ?")
            params.append(subreddit)

        if hours:
            conditions.append("created_utc >= datetime('now', '-' || ? || ' hours')")
            params.append(hours)

        if without_comments:
            conditions.append("""
                post_id NOT IN (SELECT DISTINCT post_id FROM comments)
            """)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)
        posts = []
        for row in cursor.fetchall():
            posts.append({
                'id': row[0],
                'permalink': row[1],
                'subreddit': row[2],
                'title': row[3]
            })

        conn.close()
        return posts

    def get_stats(self):
        """Get database statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        cursor.execute("SELECT COUNT(*) FROM posts")
        stats['total_posts'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM comments")
        stats['total_comments'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT post_id) FROM comments")
        stats['posts_with_comments'] = cursor.fetchone()[0]

        cursor.execute("""
            SELECT subreddit, COUNT(*) as count
            FROM posts
            GROUP BY subreddit
            ORDER BY count DESC
        """)
        stats['posts_by_subreddit'] = dict(cursor.fetchall())

        conn.close()
        return stats

    def get_stats_by_subreddit(self):
        """Get posts and comments count by subreddit

        Returns:
            List of tuples: (subreddit, post_count, comment_count)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                p.subreddit,
                COUNT(DISTINCT p.post_id) as post_count,
                COUNT(DISTINCT c.comment_id) as comment_count
            FROM posts p
            LEFT JOIN comments c ON p.post_id = c.post_id
            GROUP BY p.subreddit
            ORDER BY p.subreddit
        """)

        results = cursor.fetchall()
        conn.close()
        return results

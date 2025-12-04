# Reddit Scraper Dockerfile
# Based on rss-scraper reference implementation
# Optimized for sequential processing (no parallel workers)

FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
# Note: reddit-scraper has two Python files (unlike rss-scraper's single file)
COPY simple_scraper.py .
COPY database.py .

# Copy configuration file
# Note: reddit-scraper uses a single config.yml file (not a config/ directory)
COPY config.yml .

# Environment configuration
ENV PYTHONUNBUFFERED=1

# Run the scraper
# Note: Entry point is simple_scraper.py (not rss_scraper.py)
CMD ["python", "simple_scraper.py"]

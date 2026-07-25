import os
import time
from scout_ai.main import SEARCH_QUERIES
from scout_ai.scraper import get_feeds

def check():
    print(f"Checking data at {time.strftime('%H:%M:%S')}")
    urls = [f"https://news.google.com/rss/search?q={q.replace(' ', '+')}+when:2d&hl=en-US" for q in SEARCH_QUERIES]
    articles = get_feeds(urls)
    print(f"Found {len(articles)} articles in total.\n")

    for i, a in enumerate(articles[:15]):
        print(f"--- ARTICLE {i+1} ---")
        print(f"TITLE: {a['title']}")
        print(f"SNIPPET: {a['snippet'][:250]}...")
        print("-" * 20)

if __name__ == "__main__":
    check()

import feedparser
import requests
import re
from typing import List, Optional

KEYWORDS = ["tipp", "wette", "quote", "über 2.5", "unter 2.5", "handicap", "sieg", "over", "under", "betting", "odds"]

def filter_text(raw_text: str) -> Optional[str]:
    """
    Checks if keywords are present and returns relevant snippets.
    """
    text_lower = raw_text.lower()
    if not any(kw in text_lower for kw in KEYWORDS):
        return None

    # Split into sentences or paragraphs to extract relevant parts
    sentences = re.split(r'[.!?\n]', raw_text)
    relevant_snippets = []

    for sentence in sentences:
        if any(kw in sentence.lower() for kw in KEYWORDS):
            relevant_snippets.append(sentence.strip())

    return " ".join(relevant_snippets[:5]) if relevant_snippets else None

def get_feeds(feed_urls: List[str]) -> List[dict]:
    """
    Fetches RSS feeds and returns a list of candidate articles.
    """
    articles = []
    for url in feed_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            content = entry.get("summary", "") + " " + entry.get("description", "")
            filtered = filter_text(content)
            if filtered:
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "snippet": filtered
                })
    return articles

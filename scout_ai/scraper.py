import feedparser
import re
import time
import requests
from datetime import datetime, timedelta
from typing import List, Optional
import html

# Erweiterte Keywords für globale Erfassung
KEYWORDS = [
    "tipp", "wette", "quote", "sieg", "handicap", "over", "under", "über 2.5",
    "odds", "picks", "prediction", "best bet", "sharp money", "value",
    "lineup", "injury", "suspended", "rotation", "analysis", "preview"
]

def clean_text(text: str) -> str:
    """Bereinigt Text radikal von HTML, Tags und technischem Müll."""
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'oc=\d+.*?target="_blank"', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_feeds(feed_urls: List[str]) -> List[dict]:
    """Sammelt und filtert Artikel. Nutzt User-Agent für Reddit & Co."""
    articles = []
    now = datetime.now()
    cutoff = now - timedelta(hours=48)

    # User-Agent, um nicht als Bot geblockt zu werden (wichtig für Reddit)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    for url in feed_urls:
        try:
            # Für Reddit und andere sensible Seiten nutzen wir requests als Proxy für feedparser
            resp = requests.get(url, headers=headers, timeout=15)
            feed = feedparser.parse(resp.content)

            for entry in feed.entries[:15]:
                title = clean_text(entry.get("title", ""))
                summary = clean_text(entry.get("summary", ""))
                description = clean_text(entry.get("description", ""))
                full_content = f"{title} {summary} {description}"

                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published = datetime.fromtimestamp(time.mktime(entry.published_parsed))

                if published and published < cutoff:
                    continue

                if not any(kw in full_content.lower() for kw in KEYWORDS):
                    continue

                articles.append({
                    "title": title,
                    "snippet": full_content,
                    "link": entry.get("link", "")
                })
        except Exception:
            continue

    unique_articles = {a['title']: a for a in articles}.values()
    return list(unique_articles)

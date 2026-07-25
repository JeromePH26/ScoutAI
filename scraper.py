import feedparser
import hashlib
import html
import random
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urlparse

import requests

try:
    from scout_ai.source_registry import Source
except ImportError:
    from source_registry import Source


KEYWORDS = (
    "confirmed", "official", "ruled out", "doubtful", "questionable",
    "injury", "suspended", "starting lineup", "confirmed lineup", "late change",
    "sharp money", "line movement", "odds shortened", "odds drift",
    "unusual volume", "weather warning", "heavy rain", "strong wind",
    "handicap", "over", "under", "player prop", "team news", "rotation",
)

USER_AGENT = "ScoutAI/3.0 (RSS intelligence reader; contact: admin@example.invalid)"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.1",
})

_domain_last_request: dict[str, float] = {}
_domain_failures: dict[str, int] = {}
_cache_headers: dict[str, dict[str, str]] = {}


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _respect_domain_spacing(url: str) -> None:
    domain = _domain(url)
    minimum = 2.0
    elapsed = time.monotonic() - _domain_last_request.get(domain, 0.0)
    if elapsed < minimum:
        time.sleep(minimum - elapsed + random.uniform(0.05, 0.35))
    _domain_last_request[domain] = time.monotonic()


def _conditional_headers(url: str) -> dict[str, str]:
    return dict(_cache_headers.get(url, {}))


def _remember_cache_headers(url: str, response: requests.Response) -> None:
    headers: dict[str, str] = {}
    if response.headers.get("ETag"):
        headers["If-None-Match"] = response.headers["ETag"]
    if response.headers.get("Last-Modified"):
        headers["If-Modified-Since"] = response.headers["Last-Modified"]
    if headers:
        _cache_headers[url] = headers


def _published_iso(entry) -> str | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc).isoformat()
            except Exception:
                pass
    for attr in ("published", "updated"):
        value = entry.get(attr)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    return None


def _fingerprint(title: str, link: str, snippet: str) -> str:
    normalized = re.sub(r"\W+", " ", f"{title} {link} {snippet[:300]}".lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _fetch_feed(source: Source) -> bytes | None:
    url = source.url
    domain = _domain(url)
    failures = _domain_failures.get(domain, 0)
    if failures >= 4:
        print(f"[FETCH][COOLDOWN] {domain}: zu viele Fehler, Quelle übersprungen.")
        return None

    _respect_domain_spacing(url)
    try:
        response = SESSION.get(url, headers=_conditional_headers(url), timeout=(5, 20), allow_redirects=True)
        if response.status_code == 304:
            return None
        if response.status_code in {403, 429}:
            _domain_failures[domain] = failures + 1
            print(f"[FETCH][BLOCKED] {source.name}: HTTP {response.status_code}; kein Umgehungsversuch.")
            return None
        response.raise_for_status()
        if len(response.content) > 5_000_000:
            print(f"[FETCH][SKIP] {source.name}: Feed zu groß.")
            return None
        _remember_cache_headers(url, response)
        _domain_failures[domain] = 0
        return response.content
    except requests.RequestException as exc:
        _domain_failures[domain] = failures + 1
        print(f"[FETCH][ERROR] {source.name}: {type(exc).__name__}: {exc}")
        return None


def get_feeds(sources: Iterable[Source], max_age_hours: int = 48) -> list[dict]:
    articles: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    for source in sources:
        payload = _fetch_feed(source)
        if not payload:
            continue

        feed = feedparser.parse(payload)
        if getattr(feed, "bozo", False) and not feed.entries:
            print(f"[FEED][ERROR] {source.name}: Feed konnte nicht gelesen werden.")
            continue

        for entry in feed.entries[:30]:
            title = clean_text(entry.get("title", ""))
            summary = clean_text(entry.get("summary", ""))
            description = clean_text(entry.get("description", ""))
            full = f"{title} {summary} {description}".strip()
            if not title or len(full) < 40:
                continue

            published_at = _published_iso(entry)
            if published_at:
                try:
                    if datetime.fromisoformat(published_at) < cutoff:
                        continue
                except ValueError:
                    pass

            lower = full.lower()
            if source.category not in {"wire", "analytics"} and not any(k in lower for k in KEYWORDS):
                continue

            link = entry.get("link", "")
            articles.append({
                "title": title,
                "snippet": full[:3500],
                "link": link,
                "source": source.name,
                "source_category": source.category,
                "source_tier": source.tier,
                "source_quality_hint": source.quality,
                "published_at": published_at,
                "content_fingerprint": _fingerprint(title, link, full),
            })

    # Exakte Kopien und nahezu identische Syndication-Einträge vor dem Clustering entfernen.
    unique: dict[str, dict] = {}
    for article in articles:
        key = article["content_fingerprint"]
        current = unique.get(key)
        if current is None or article["source_quality_hint"] > current["source_quality_hint"]:
            unique[key] = article
    return list(unique.values())

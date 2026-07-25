from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    category: str
    tier: str = "B"
    language: str = "en"
    region: str = "global"
    quality: float = 0.60
    interval_minutes: int = 30
    enabled: bool = True


# V1: bewusst kleine, kontrollierbare Startliste. Danach anhand realer Performance erweitern.
SOURCES: tuple[Source, ...] = (
    Source("ESPN", "https://www.espn.com/espn/rss/news", "wire", "A", quality=0.88, interval_minutes=10),
    Source("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml", "wire", "A", quality=0.92, interval_minutes=10),
    Source("Sky Sports", "https://www.skysports.com/rss/12040", "wire", "A", quality=0.86, interval_minutes=15),
    Source("The Guardian Football", "https://www.theguardian.com/football/rss", "media", "A", quality=0.84, interval_minutes=15),
    Source("Reuters Sports Discovery", "https://news.google.com/rss/search?q=site%3Areuters.com+sports+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "discovery", "A", quality=0.94, interval_minutes=15),
    Source("AP Sports Discovery", "https://news.google.com/rss/search?q=site%3Aapnews.com+sports+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "discovery", "A", quality=0.92, interval_minutes=15),
    Source("Opta Analyst Discovery", "https://news.google.com/rss/search?q=site%3Atheanalyst.com+football+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen", "analytics", "B", quality=0.88, interval_minutes=30),
    Source("StatsBomb Discovery", "https://news.google.com/rss/search?q=site%3Astatsbomb.com+football+when%3A7d&hl=en-US&gl=US&ceid=US%3Aen", "analytics", "B", quality=0.88, interval_minutes=60),
    Source("Covers Discovery", "https://news.google.com/rss/search?q=site%3Acovers.com+picks+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "experts", "B", quality=0.68, interval_minutes=30),
    Source("Action Network Discovery", "https://news.google.com/rss/search?q=site%3Aactionnetwork.com+picks+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "experts", "B", quality=0.72, interval_minutes=30),
    Source("BettingExpert Discovery", "https://news.google.com/rss/search?q=site%3Abettingexpert.com+tips+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "experts", "C", quality=0.58, interval_minutes=60),
    Source("OLBG Discovery", "https://news.google.com/rss/search?q=site%3Aolbg.com+tips+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "experts", "C", quality=0.55, interval_minutes=60),
    Source("Oddschecker Discovery", "https://news.google.com/rss/search?q=site%3Aoddschecker.com+tips+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "market", "B", quality=0.70, interval_minutes=30),
    Source("Betfair Hub", "https://www.betfair.com/hub/feed/", "market", "B", quality=0.72, interval_minutes=30),
    Source("Reddit Soccer Betting", "https://www.reddit.com/r/soccerbetting/.rss", "community", "D", quality=0.38, interval_minutes=60),
    Source("Reddit Sportsbook", "https://www.reddit.com/r/sportsbook/.rss", "community", "D", quality=0.36, interval_minutes=60),
    Source("HLTV", "https://www.hltv.org/rss/news", "esports", "B", quality=0.78, interval_minutes=20),
    Source("Google Lineups", "https://news.google.com/rss/search?q=%22confirmed+lineup%22+football+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "discovery", "A", quality=0.68, interval_minutes=10),
    Source("Google Injuries", "https://news.google.com/rss/search?q=%22ruled+out%22+football+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "discovery", "A", quality=0.68, interval_minutes=10),
    Source("Google Odds Movement", "https://news.google.com/rss/search?q=%22odds+shortened%22+OR+%22line+movement%22+when%3A1d&hl=en-US&gl=US&ceid=US%3Aen", "discovery", "B", quality=0.62, interval_minutes=15),
)


def enabled_sources() -> list[Source]:
    return [source for source in SOURCES if source.enabled]


def by_tier(tier: str) -> list[Source]:
    return [source for source in enabled_sources() if source.tier == tier]


def urls(sources: Iterable[Source]) -> list[str]:
    return [source.url for source in sources]

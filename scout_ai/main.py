import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Iterable, Mapping

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from scout_ai.ai_analyzer import analyze_snippet
    from scout_ai.consensus_engine import build_consensus_bundle, rank_consensus
    from scout_ai.database import init_db, process_consensus
    from scout_ai.entity_resolver import build_default_resolver
    from scout_ai.event_clusterer import cluster_events
    from scout_ai.notifier import send_telegram_alert
    from scout_ai.scraper import get_feeds
    from scout_ai.source_registry import enabled_sources
except ImportError:
    from ai_analyzer import analyze_snippet
    from consensus_engine import build_consensus_bundle, rank_consensus
    from database import init_db, process_consensus
    from entity_resolver import build_default_resolver
    from event_clusterer import cluster_events
    from notifier import send_telegram_alert
    from scraper import get_feeds
    from source_registry import enabled_sources


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MAX_AI_CALLS_PER_PULSE = int(os.getenv("MAX_AI_CALLS_PER_PULSE", "5"))
MAX_ARTICLES_PER_CLUSTER = int(os.getenv("MAX_ARTICLES_PER_CLUSTER", "8"))
PULSE_SECONDS = int(os.getenv("PULSE_SECONDS", "300"))
EVENT_CLUSTER_SIMILARITY = float(os.getenv("EVENT_CLUSTER_SIMILARITY", "0.52"))
EVENT_CLUSTER_MAX_GAP_HOURS = float(
    os.getenv("EVENT_CLUSTER_MAX_GAP_HOURS", "72")
)
AI_CLUSTER_COOLDOWN_SECONDS = int(
    os.getenv("AI_CLUSTER_COOLDOWN_SECONDS", "21600")
)

ENTITY_RESOLVER = build_default_resolver()
_last_source_run: dict[str, float] = {}
_analyzed_clusters: dict[str, float] = {}


def _due_sources() -> list:
    now = time.time()
    due = []
    for source in enabled_sources():
        last = _last_source_run.get(source.name, 0.0)
        if now - last >= source.interval_minutes * 60:
            due.append(source)
            _last_source_run[source.name] = now
    return due


def _cluster_due(cluster_id: str, *, now: float | None = None) -> bool:
    if not cluster_id:
        return False
    current = now if now is not None else time.time()
    last = _analyzed_clusters.get(cluster_id)
    return last is None or current - last >= AI_CLUSTER_COOLDOWN_SECONDS


def _remember_cluster(cluster_id: str, *, now: float | None = None) -> None:
    if cluster_id:
        _analyzed_clusters[cluster_id] = now if now is not None else time.time()


def _cluster_source_label(cluster: object) -> str:
    sources = getattr(cluster, "sources", set()) or set()
    if isinstance(sources, str):
        return sources
    values = sorted(str(source) for source in sources if str(source).strip())
    return ", ".join(values) or "Event Consensus"


def _valid_signal(signal: object) -> bool:
    return isinstance(signal, Mapping) and signal.get("status") in {"ACTION", "WATCH"}


def _publish_signal(signal: dict, cluster: object, decision: object) -> bool:
    status = str(signal.get("status") or "REJECT")
    match = str(signal.get("match") or "UNKNOWN").strip()
    market = signal.get("market") or {}
    if not isinstance(market, Mapping):
        market = {}
    bet = str(market.get("bet") or "NO_MARKET").strip()

    if not match or match.upper() == "UNKNOWN":
        print("[SIGNAL][SKIP] Gemini lieferte kein konkretes Match.")
        return False

    if status == "ACTION" and not market.get("market_odds"):
        signal["status"] = "WATCH"
        status = "WATCH"

    decision_data = decision.as_dict()
    signal["event_cluster_id"] = decision.cluster_id
    signal["event_consensus"] = decision_data
    signal["source_count"] = decision.independent_sources
    signal["article_count"] = decision.article_count
    signal["consensus_reached"] = (
        f"{status} | EVENT {decision.confidence}/100 | "
        f"{decision.independent_sources} unabhängige Quellen"
    )

    source_label = _cluster_source_label(cluster)
    _, is_new = process_consensus(match, bet, source_label, signal)
    if not is_new:
        print(f"[SIGNAL][DUPLICATE] {match} | {bet}")
        return False

    send_telegram_alert(signal)
    print(f"[SIGNAL] {status}: {match} | {bet}")
    return True


def process_articles(articles: Iterable[Mapping[str, object]]) -> dict[str, int]:
    article_list = [dict(article) for article in articles]
    clusters = cluster_events(
        article_list,
        resolver=ENTITY_RESOLVER,
        similarity_threshold=EVENT_CLUSTER_SIMILARITY,
        max_time_gap_hours=EVENT_CLUSTER_MAX_GAP_HOURS,
    )
    ranked = rank_consensus(clusters)

    stats = {
        "articles": len(article_list),
        "clusters": len(clusters),
        "analyze": sum(decision.decision == "ANALYZE" for _, decision in ranked),
        "watch": sum(decision.decision == "WATCH" for _, decision in ranked),
        "skip": sum(decision.decision == "SKIP" for _, decision in ranked),
        "ai_calls": 0,
        "signals": 0,
    }

    print(
        f"[EVENT] Artikel={stats['articles']} Cluster={stats['clusters']} "
        f"Analyze={stats['analyze']} Watch={stats['watch']} Skip={stats['skip']}"
    )

    for cluster, decision in ranked:
        print(
            f"[CONSENSUS] {decision.cluster_id} n={decision.article_count} "
            f"sources={decision.independent_sources} confidence={decision.confidence} "
            f"decision={decision.decision}"
        )

        if not decision.ready_for_ai:
            continue
        if stats["ai_calls"] >= MAX_AI_CALLS_PER_PULSE:
            print("[CONSENSUS] Gemini-Budget erreicht.")
            break
        if not _cluster_due(decision.cluster_id):
            print(f"[CONSENSUS][COOLDOWN] {decision.cluster_id} wurde bereits analysiert.")
            continue

        _remember_cluster(decision.cluster_id)
        stats["ai_calls"] += 1
        bundle = build_consensus_bundle(
            cluster,
            decision,
            max_articles=MAX_ARTICLES_PER_CLUSTER,
        )
        analyses = analyze_snippet(bundle, is_bundle=True)
        if not isinstance(analyses, list):
            logging.error("AI analyzer returned a non-list response")
            continue

        for raw_signal in analyses:
            if not _valid_signal(raw_signal):
                continue
            signal = dict(raw_signal)
            if _publish_signal(signal, cluster, decision):
                stats["signals"] += 1

    return stats


def pulse_check() -> dict[str, int]:
    sources = _due_sources()
    if not sources:
        print("[DISCOVERY] Noch keine Quelle fällig.")
        return {
            "articles": 0,
            "clusters": 0,
            "analyze": 0,
            "watch": 0,
            "skip": 0,
            "ai_calls": 0,
            "signals": 0,
        }

    print(
        f"\n[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
        f"GLOBAL EVENT PULSE | Quellen={len(sources)}"
    )
    articles = get_feeds(sources)
    if not articles:
        print("[DISCOVERY] Keine neuen relevanten Artikel.")
        return {
            "articles": 0,
            "clusters": 0,
            "analyze": 0,
            "watch": 0,
            "skip": 0,
            "ai_calls": 0,
            "signals": 0,
        }

    return process_articles(articles)


def main() -> None:
    init_db()
    print("=== SCOUT-AI EVENT CONSENSUS v4.0 ===")
    print(f"[REGISTRY] {len(enabled_sources())} Startquellen geladen.")
    print(
        f"[PIPELINE] Entity Resolver -> Event Clusterer -> Consensus Engine -> Gemini | "
        f"AI-Limit={MAX_AI_CALLS_PER_PULSE}"
    )

    while True:
        try:
            pulse_check()
        except Exception:
            logging.exception("Critical event pulse error")
        time.sleep(PULSE_SECONDS)


if __name__ == "__main__":
    main()

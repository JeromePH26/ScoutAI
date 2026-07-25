import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Iterable, Mapping

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from scout_ai.consensus_engine import rank_consensus
    from scout_ai.database import init_db, process_consensus
    from scout_ai.entity_resolver import build_default_resolver
    from scout_ai.event_clusterer import cluster_events
    from scout_ai.notifier import send_telegram_alert
    from scout_ai.rule_signal_engine import build_rule_signals
    from scout_ai.scraper import get_feeds
    from scout_ai.source_registry import enabled_sources
except ImportError:
    from consensus_engine import rank_consensus
    from database import init_db, process_consensus
    from entity_resolver import build_default_resolver
    from event_clusterer import cluster_events
    from notifier import send_telegram_alert
    from rule_signal_engine import build_rule_signals
    from scraper import get_feeds
    from source_registry import enabled_sources


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PULSE_SECONDS = int(os.getenv("PULSE_SECONDS", "300"))
EVENT_CLUSTER_SIMILARITY = float(os.getenv("EVENT_CLUSTER_SIMILARITY", "0.52"))
EVENT_CLUSTER_MAX_GAP_HOURS = float(
    os.getenv("EVENT_CLUSTER_MAX_GAP_HOURS", "72")
)
MAX_RULE_SIGNALS_PER_PULSE = int(
    os.getenv("MAX_RULE_SIGNALS_PER_PULSE", "10")
)
SIGNAL_CLUSTER_COOLDOWN_SECONDS = int(
    os.getenv("SIGNAL_CLUSTER_COOLDOWN_SECONDS", "21600")
)

ENTITY_RESOLVER = build_default_resolver()
_last_source_run: dict[str, float] = {}
_processed_clusters: dict[str, float] = {}


def _empty_stats() -> dict[str, int]:
    return {
        "articles": 0,
        "clusters": 0,
        "analyze": 0,
        "watch": 0,
        "skip": 0,
        "rule_evaluations": 0,
        "signals": 0,
    }


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
    last = _processed_clusters.get(cluster_id)
    return last is None or current - last >= SIGNAL_CLUSTER_COOLDOWN_SECONDS


def _remember_cluster(cluster_id: str, *, now: float | None = None) -> None:
    if cluster_id:
        _processed_clusters[cluster_id] = now if now is not None else time.time()


def _cluster_source_label(cluster: object) -> str:
    sources = getattr(cluster, "sources", set()) or set()
    if isinstance(sources, str):
        return sources
    values = sorted(str(source) for source in sources if str(source).strip())
    return ", ".join(values) or "ScoutAI Rule Consensus"


def _publish_signal(signal: dict, cluster: object, decision: object) -> bool:
    status = str(signal.get("status") or "WATCH").upper()
    if status != "WATCH":
        # Die KI-freie Version darf aktuell keine ACTION-Wetten erzeugen.
        signal["status"] = "WATCH"
        status = "WATCH"

    match = str(signal.get("match") or "UNKNOWN").strip()
    if not match or match.upper() == "UNKNOWN":
        print("[SIGNAL][SKIP] Kein eindeutig erkanntes Spiel.")
        return False

    market = signal.get("market") or {}
    if not isinstance(market, Mapping):
        market = {}
    bet_key = str(
        market.get("bet")
        or f"INTELLIGENCE_{signal.get('signal_type', 'CONSENSUS')}"
    ).strip()

    signal["event_cluster_id"] = str(
        signal.get("event_cluster_id")
        or getattr(decision, "cluster_id", "")
    )
    signal["event_consensus"] = decision.as_dict()
    signal["source_count"] = int(
        getattr(decision, "independent_sources", 0) or 0
    )
    signal["article_count"] = int(
        getattr(decision, "article_count", 0) or 0
    )
    signal["consensus_reached"] = (
        f"WATCH | RULE {getattr(decision, 'confidence', 0)}/100 | "
        f"{getattr(decision, 'independent_sources', 0)} unabhängige Quellen"
    )

    source_label = _cluster_source_label(cluster)
    _, is_new = process_consensus(match, bet_key, source_label, signal)
    if not is_new:
        print(f"[SIGNAL][DUPLICATE] {match} | {bet_key}")
        return False

    send_telegram_alert(signal)
    print(
        f"[SIGNAL] WATCH: {match} | "
        f"{signal.get('signal_type', 'CONSENSUS')}"
    )
    return True


def process_articles(
    articles: Iterable[Mapping[str, object]],
) -> dict[str, int]:
    article_list = [dict(article) for article in articles]
    clusters = cluster_events(
        article_list,
        resolver=ENTITY_RESOLVER,
        similarity_threshold=EVENT_CLUSTER_SIMILARITY,
        max_time_gap_hours=EVENT_CLUSTER_MAX_GAP_HOURS,
    )
    ranked = rank_consensus(clusters)

    stats = _empty_stats()
    stats["articles"] = len(article_list)
    stats["clusters"] = len(clusters)
    stats["analyze"] = sum(
        decision.decision == "ANALYZE" for _, decision in ranked
    )
    stats["watch"] = sum(
        decision.decision == "WATCH" for _, decision in ranked
    )
    stats["skip"] = sum(
        decision.decision == "SKIP" for _, decision in ranked
    )

    print(
        f"[EVENT] Artikel={stats['articles']} Cluster={stats['clusters']} "
        f"Analyze={stats['analyze']} Watch={stats['watch']} "
        f"Skip={stats['skip']}"
    )

    for cluster, decision in ranked:
        print(
            f"[CONSENSUS] {decision.cluster_id} "
            f"n={decision.article_count} "
            f"sources={decision.independent_sources} "
            f"confidence={decision.confidence} "
            f"decision={decision.decision}"
        )

        if decision.decision != "ANALYZE":
            continue
        if stats["signals"] >= MAX_RULE_SIGNALS_PER_PULSE:
            print("[RULE] Signal-Limit für diesen Durchlauf erreicht.")
            break
        if not _cluster_due(decision.cluster_id):
            print(
                f"[RULE][COOLDOWN] {decision.cluster_id} "
                "wurde bereits verarbeitet."
            )
            continue

        stats["rule_evaluations"] += 1
        signals = build_rule_signals(cluster, decision)
        _remember_cluster(decision.cluster_id)

        for signal in signals:
            if _publish_signal(dict(signal), cluster, decision):
                stats["signals"] += 1

    return stats


def pulse_check() -> dict[str, int]:
    sources = _due_sources()
    if not sources:
        print("[DISCOVERY] Noch keine Quelle fällig.")
        return _empty_stats()

    print(
        f"\n[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
        f"GLOBAL RULE PULSE | Quellen={len(sources)}"
    )
    articles = get_feeds(sources)
    if not articles:
        print("[DISCOVERY] Keine neuen relevanten Artikel.")
        return _empty_stats()

    return process_articles(articles)


def main() -> None:
    init_db()
    print("=== SCOUT-AI RULE CONSENSUS v5.0 – OHNE KI ===")
    print(f"[REGISTRY] {len(enabled_sources())} Startquellen geladen.")
    print(
        "[PIPELINE] Quellen -> Entity Resolver -> Event Clusterer -> "
        "Consensus Engine -> Rule Signal Engine -> Telegram"
    )
    print(
        "[SAFETY] Regelbetrieb erzeugt nur WATCH. "
        "Keine faire Quote, kein EV und keine automatische Wettfreigabe."
    )

    while True:
        try:
            stats = pulse_check()
            print(
                f"[PULSE] rule_evaluations={stats['rule_evaluations']} "
                f"signals={stats['signals']}"
            )
        except Exception:
            logging.exception("Critical rule pulse error")
        time.sleep(PULSE_SECONDS)


if __name__ == "__main__":
    main()

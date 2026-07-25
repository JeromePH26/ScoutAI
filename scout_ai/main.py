import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from scout_ai.ai_analyzer import analyze_snippet
    from scout_ai.database import init_db, process_consensus
    from scout_ai.notifier import send_telegram_alert
    from scout_ai.quant_engine import build_compact_bundle, cluster_articles, rank_clusters
    from scout_ai.scraper import get_feeds
    from scout_ai.source_registry import by_tier, enabled_sources
except ImportError:
    from ai_analyzer import analyze_snippet
    from database import init_db, process_consensus
    from notifier import send_telegram_alert
    from quant_engine import build_compact_bundle, cluster_articles, rank_clusters
    from scraper import get_feeds
    from source_registry import by_tier, enabled_sources


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MAX_AI_CALLS_PER_PULSE = int(os.getenv("MAX_AI_CALLS_PER_PULSE", "5"))
MAX_ARTICLES_PER_CLUSTER = int(os.getenv("MAX_ARTICLES_PER_CLUSTER", "8"))
PULSE_SECONDS = int(os.getenv("PULSE_SECONDS", "300"))

_last_tier_run: dict[str, float] = {}


def _due_sources() -> list:
    now = time.time()
    due = []
    for source in enabled_sources():
        last = _last_tier_run.get(source.name, 0.0)
        if now - last >= source.interval_minutes * 60:
            due.append(source)
            _last_tier_run[source.name] = now
    return due


def pulse_check() -> None:
    sources = _due_sources()
    if not sources:
        print("[DISCOVERY] Noch keine Quelle fällig.")
        return

    print(
        f"\n[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
        f"GLOBAL PULSE | Quellen={len(sources)}"
    )
    articles = get_feeds(sources)
    if not articles:
        print("[DISCOVERY] Keine neuen relevanten Artikel.")
        return

    clusters = cluster_articles(articles)
    ranked = rank_clusters(clusters)
    print(
        f"[QUANT] Artikel={len(articles)} Cluster={len(clusters)} "
        f"Analyze={sum(score.decision == 'ANALYZE' for _, score in ranked)} "
        f"Watch={sum(score.decision == 'WATCH' for _, score in ranked)}"
    )

    calls = 0
    for cluster, score in ranked:
        print(
            f"[QUANT] {score.fingerprint} n={score.article_count} "
            f"sources={score.independent_sources} confidence={score.confidence} "
            f"decision={score.decision}"
        )
        if score.decision != "ANALYZE":
            continue
        if calls >= MAX_AI_CALLS_PER_PULSE:
            print("[QUANT] Gemini-Budget erreicht.")
            break

        calls += 1
        bundle = build_compact_bundle(cluster, score, MAX_ARTICLES_PER_CLUSTER)
        analyses = analyze_snippet(bundle, is_bundle=True)

        for signal in analyses:
            status = signal.get("status")
            if status not in {"ACTION", "WATCH"}:
                continue

            signal["local_quant"] = score.as_dict()
            signal["source_count"] = score.independent_sources
            signal["article_count"] = score.article_count
            match = signal.get("match", "UNKNOWN")
            market = signal.get("market") or {}
            bet = market.get("bet", "NO_MARKET")

            # Ohne echte Marktquote wird niemals ACTION erzwungen.
            if status == "ACTION" and not market.get("market_odds"):
                signal["status"] = "WATCH"
                status = "WATCH"

            _, is_new = process_consensus(match, bet, "Global Consensus v3", signal)
            if is_new:
                signal["consensus_reached"] = (
                    f"{status} | LOCAL {score.confidence}/100 | "
                    f"{score.independent_sources} unabhängige Quellen"
                )
                send_telegram_alert(signal)
                print(f"[SIGNAL] {status}: {match} | {bet}")


def main() -> None:
    init_db()
    print("=== SCOUT-AI GLOBAL CONSENSUS v3.0 ===")
    print(f"[REGISTRY] {len(enabled_sources())} Startquellen geladen.")

    while True:
        try:
            pulse_check()
        except Exception:
            logging.exception("Critical pulse error")
        time.sleep(PULSE_SECONDS)


if __name__ == "__main__":
    main()

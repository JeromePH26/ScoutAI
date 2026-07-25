import time
import os
import json
import logging
import sys
import random

# Absoluter Import-Pfad für Server-Umgebungen
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    filename='scout_ai/debug.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

try:
    from scout_ai.scraper import get_feeds
    from scout_ai.ai_analyzer import analyze_snippet
    from scout_ai.database import init_db, process_consensus
    from scout_ai.notifier import send_telegram_alert
except ImportError:
    # Fallback für lokale Ausführung
    from scraper import get_feeds
    from ai_analyzer import analyze_snippet
    from database import init_db, process_consensus
    from notifier import send_telegram_alert

# --- SPY-MASTER MATRIX v5.6 ---
SHADOW = ['site:twitter.com "confirmed" "injury" football', 'site:twitter.com "lineup leak"', '"betfair exchange" "unusual volume"']
COMMUNITY = ["https://www.reddit.com/r/soccerbetting/.rss", "https://www.reddit.com/r/sportsbook/.rss", "https://www.reddit.com/r/mma/.rss"]
GLOBAL = ["best bets expert analysis", "asian handicap picks today", "nba player props predictions", "football statistical analysis"]
WIRES = ["https://www.espn.com/espn/rss/news", "https://www.hltv.org/rss/news", "https://www.betfair.com/hub/feed/"]

def pulse_check(queries, mode_name, is_search=False):
    print(f"[{time.strftime('%H:%M:%S')}] PULSE: Gathering {mode_name}...")

    if is_search:
        target_urls = [f"https://news.google.com/rss/search?q={q.replace(' ', '+')}+when:1d&hl=en-US" for q in queries]
    else:
        target_urls = queries

    articles = get_feeds(target_urls)
    if not articles: return

    bundle_text = ""
    for i, art in enumerate(articles[:30]):
        bundle_text += f"\n--- QUELLE {i+1} ({art.get('title')}) ---\n{art.get('snippet')}\n"

    print(f"   [*] AI-BUNDLE-ANALYSIS: {min(len(articles), 30)}/30 Top-Quellen werden verglichen...", end=" ")

    analyses = analyze_snippet(bundle_text, is_bundle=True)

    if analyses and isinstance(analyses, list):
        print(f"[+] {len(analyses)} SIGNALE GEFUNDEN")
        for signal in analyses:
            if signal.get("status") == "ACCEPT":
                match = signal.get("match", "Unknown")
                bet = signal.get("recommendation", {}).get("bet", "Unknown")

                _, is_new = process_consensus(match, bet, "Cross-Ref Engine", signal)

                if is_new:
                    print(f"   [!!!] SIGNAL FIRED: {match}")
                    signal["consensus_reached"] = f"CROSS-REFERENCED ({mode_name})"
                    send_telegram_alert(signal)
    else:
        print("[-] KEIN VALIDER KONSENS")

def main():
    init_db()
    print("=== SCOUT-AI MASTERMIND v5.9 | RAILWAY EDITION ===")

    while True:
        try:
            tasks = [
                (SHADOW, "SHADOW-LEAKS", True),
                (COMMUNITY, "REDDIT-FEED", False),
                (GLOBAL, "GLOBAL-MARKET", True),
                (WIRES, "INSTITUTIONAL-WIRE", False)
            ]
            random.shuffle(tasks)

            for queries, name, is_search in tasks:
                pulse_check(queries, name, is_search)
                wait = random.randint(45, 90)
                time.sleep(wait)

        except Exception as e:
            logging.error(f"Critical Loop Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()

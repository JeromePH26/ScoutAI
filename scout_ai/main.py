import time
import os
from scraper import get_feeds
from ai_analyzer import analyze_snippet
from database import init_db, is_duplicate, save_pick
from notifier import send_telegram_alert

# Example RSS feeds (broad coverage)
FEED_URLS = [
    "https://news.google.com/rss/search?q=sportwetten+tipps+prognose&hl=de&gl=DE&ceid=DE:de",
    "https://news.google.com/rss/search?q=betting+tips+predictions&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=esports+betting+tips+cs2+lol&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=ufc+mma+betting+tips&hl=en-US&gl=US&ceid=US:en"
]

def run_cycle():
    print(f"[{time.strftime('%H:%M:%S')}] Starting search for new tips...")

    # 1. Scrape
    articles = get_feeds(FEED_URLS)

    for article in articles:
        # 2. Analyze with AI
        analysis = analyze_snippet(article["snippet"])

        if analysis and isinstance(analysis, dict):
            home = analysis.get("home_team")
            away = analysis.get("away_team")
            bet = analysis.get("recommended_bet")
            score = analysis.get("confidence_score", 0)

            # 3. Hard Filter: Validate required fields and confidence threshold
            if not home or not away or not bet or home == "Team A" or home == "Unknown":
                # Check for "Team A" as it's the placeholder in the prompt
                print(f"Skipping: Incomplete or placeholder data for {home} vs {away}")
                continue

            if score < 75:
                print(f"Skipping: Confidence too low ({score}%) for {home} vs {away}")
                continue

            match_str = f"{home} vs {away}"

            # 4. Check for duplicates (using match_str as identifier)
            if not is_duplicate(match_str, "ScoutAI_Engine", bet):
                # 5. Save and Notify
                save_pick(match_str, "ScoutAI_Engine", bet)
                send_telegram_alert(analysis)
            else:
                print(f"Skipping duplicate: {match_str}")

def main():
    init_db()
    print("ScoutAI System started...")

    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"Error in main loop: {e}")

        # Wait 30 minutes before next run to stay within free tier limits
        print("Sleeping for 30 minutes...")
        time.sleep(1800)

if __name__ == "__main__":
    main()

import os
import requests
from dotenv import load_dotenv

load_dotenv()

def get_sport_icon(sport_name: str) -> str:
    """
    Returns an emoji based on the sport name.
    """
    s = sport_name.lower()
    if "foot" in s or "soccer" in s: return "⚽"
    if "basket" in s: return "🏀"
    if "tennis" in s: return "🎾"
    if "e-sport" in s or "cs2" in s or "lol" in s or "dota" in s: return "🎮"
    if "mma" in s or "ufc" in s or "box" in s: return "🥊"
    if "ice" in s or "hockey" in s: return "🏒"
    if "american" in s or "nfl" in s: return "🏈"
    if "base" in s or "mlb" in s: return "⚾"
    return "📌"

def send_telegram_alert(signal_data: dict):
    """
    Sends a professionally formatted telegram message with the multi-sport betting signal.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram config missing.")
        return

    sport = signal_data.get('sport', 'General')
    icon = get_sport_icon(sport)
    home = signal_data.get('home_team', 'Unknown')
    away = signal_data.get('away_team', 'Unknown')
    league = signal_data.get('league', 'N/A')
    bet = signal_data.get('recommended_bet', 'N/A')
    odds = signal_data.get('odds', 'N/A')
    score = signal_data.get('confidence_score', 0)
    reasoning = signal_data.get('algo_reasoning', 'No reasoning provided.')

    message = (
        "🎯 *SCOUT-AI SIGNAL DETECTED*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Sport:* {icon} {sport}\n"
        f"{icon} *Match:* {home} vs {away} ({league})\n"
        f"💡 *Tipp:* {bet}\n"
        f"📊 *Quote:* {odds}\n"
        f"🔥 *Algo-Score:* {score}%\n\n"
        "🧠 *Algorithmus-Analyse:*\n"
        f"_{reasoning}_\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"Professional Alert sent for {sport}: {home} vs {away}")
    except Exception as e:
        print(f"Telegram notification failed: {e}")

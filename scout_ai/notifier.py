import os
import requests
from dotenv import load_dotenv

load_dotenv()

def escape_markdown(text: str) -> str:
    """Maskiert Sonderzeichen für Telegram Markdown v1."""
    if not isinstance(text, str): return str(text)
    # Zeichen die in Markdown v1 Probleme machen können
    chars = ['*', '_', '`', '[']
    for char in chars:
        text = text.replace(char, f'\\{char}')
    return text

def send_telegram_alert(data: dict):
    """
    MASTERMIND v5.2 INSTITUTIONAL REPORTING (Safe Markdown Edition)
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id: return

    # Daten extrahieren und für Markdown maskieren
    match = escape_markdown(data.get('match', 'N/A'))
    start = escape_markdown(data.get('start_time', 'N/A'))
    sport = escape_markdown(data.get('sport', 'N/A'))

    an = data.get('analysis', {})
    fair_odds = escape_markdown(an.get('fair_odds', 'N/A'))
    ev_percent = escape_markdown(an.get('ev_percent', 'N/A'))
    risk = escape_markdown(an.get('risk', 'N/A'))

    rec = data.get('recommendation', {})
    bet = escape_markdown(rec.get('bet', 'N/A'))
    units = escape_markdown(rec.get('units', 'N/A'))
    logic = escape_markdown(rec.get('logic', 'N/A'))

    pts = data.get('consensus_reached', '?')

    # Design
    header = "👑 *MASTERMIND SIGNAL*" if str(pts) == "SOLO" else "🏆 *GOLDEN SIGNAL*"

    message = (
        f"{header}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏟️ *MATCH:* {match}\n"
        f"⏰ *START:* {start}\n"
        f"📌 *LIGA:* {sport}\n\n"
        "📊 *QUANT ANALYSIS:*\n"
        f"• Fair Quote: {fair_odds}\n"
        f"• Erwartungswert: {ev_percent}\n"
        f"• Risiko: {risk}\n\n"
        "💡 *SYNDICATE PICK:*\n"
        f"✅ *BET:* {bet}\n"
        f"💰 *STAKE:* {units}\n"
        f"🧠 *LOGIC:* _{logic}_\n\n"
        f"🎖️ *CONSENSUS:* {pts}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Telegram Fehler: {response.text}")
    except Exception as e:
        print(f"Telegram Exception: {e}")

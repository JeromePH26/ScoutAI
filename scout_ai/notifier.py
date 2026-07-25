import html
import os

import requests
from dotenv import load_dotenv


load_dotenv()


def _text(value: object, fallback: str = "N/A") -> str:
    raw = str(value if value not in (None, "") else fallback)
    return html.escape(raw)


def _lines(values: object, limit: int = 5) -> str:
    if not isinstance(values, (list, tuple)):
        return "• Keine Angaben"
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned:
        return "• Keine Angaben"
    return "\n".join(f"• {_text(value)}" for value in cleaned[:limit])


def send_telegram_alert(data: dict) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[TELEGRAM][SKIP] TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlt.")
        return False

    status = str(data.get("status") or "WATCH").upper()
    header = "🚨 <b>SCOUTAI ACTION</b>" if status == "ACTION" else "🔎 <b>SCOUTAI WATCH</b>"

    match = _text(data.get("match"))
    sport = _text(data.get("sport"))
    league = _text(data.get("league"))
    signal_type = _text(data.get("signal_type"))
    confidence = _text(data.get("confidence"), "0")
    sources = _text(data.get("sources_supporting") or data.get("source_count"), "0")
    risk = _text(data.get("risk"), "UNKNOWN")
    reason = _text(data.get("reason"))
    facts = _lines(data.get("facts") or data.get("evidence"))
    warnings = _lines(data.get("warnings") or data.get("conflicts"))

    message = (
        f"{header}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏟️ <b>Spiel:</b> {match}\n"
        f"🏅 <b>Sport:</b> {sport}\n"
        f"🏆 <b>Wettbewerb:</b> {league}\n"
        f"📌 <b>Ereignis:</b> {signal_type}\n"
        f"📊 <b>Consensus:</b> {confidence}/100\n"
        f"📰 <b>Unabhängige Quellen:</b> {sources}\n"
        f"⚠️ <b>Risiko:</b> {risk}\n\n"
        f"<b>Bestätigte Hinweise</b>\n{facts}\n\n"
        f"<b>Offene Punkte</b>\n{warnings}\n\n"
        f"<b>Einordnung</b>\n{reason}\n\n"
        "🛑 <b>Keine Wettfreigabe:</b> Es wurden keine faire Quote "
        "und kein Expected Value berechnet.\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    message = message[:4000]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            print(f"[TELEGRAM][ERROR] {response.status_code}: {response.text}")
            return False
        return True
    except requests.RequestException as exc:
        print(f"[TELEGRAM][ERROR] {type(exc).__name__}: {exc}")
        return False

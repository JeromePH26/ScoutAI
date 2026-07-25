import os
import json
import time
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
client = None
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
    except Exception as e:
        print(f"CRITICAL: API Initialization failed: {e}")

def surgical_json_extraction(text: str):
    """Extrahiert JSON oder eine Liste von JSONs."""
    try:
        # Versuche Liste zu finden
        list_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
        if list_match:
            return json.loads(list_match.group(0))
        # Versuche einzelnes Objekt zu finden
        obj_match = re.search(r'\{.*\}', text, re.DOTALL)
        if obj_match:
            return [json.loads(obj_match.group(0))]
        return None
    except:
        return None

def analyze_snippet(snippet: str, is_bundle=False) -> list:
    if not client: return None

    current_time = time.strftime("%d.%m.%Y %H:%M")

    # Spezial-Prompt für den Vergleich von mehreren Quellen
    prompt = f"""
    ROLE: Du bist der 'Strategic Head of Quant Analysis'.
    MISSION: Vergleiche die folgenden verschiedenen Nachrichtenquellen und finde Übereinstimmungen oder versteckte Muster für Wett-Vorteile (+EV).

    SYSTEM-ZEIT: {current_time}
    INPUT-PAKET:
    {snippet}

    ANALYSE-AUFTRAG:
    1. CROSS-REFERENCE: Suchen nach dem GLEICHEN Spiel in verschiedenen Quellen.
    2. PATTERN RECOGNITION: Wenn Quelle A eine Verletzung meldet und Quelle B einen Quotensturz, verbinde diese zu einem Signal.
    3. CONFLICT CHECK: Wenn Quellen sich widersprechen, sei extrem vorsichtig (Risk High).
    4. VALIDIERUNG: Nur Spiele in der ZUKUNFT.

    AUSGABE-FORMAT (GIB EINE LISTE VON JSON-OBJEKTEN ZURÜCK):
    [
      {{
        "status": "ACCEPT",
        "reason": "Zusammenfassender Grund des Vergleichs (z.B. Verletzung + Quotensturz bestätigt)",
        "match": "Team A vs Team B",
        "start_time": "Zeit",
        "sport": "Liga",
        "analysis": {{ "fair_odds": "X", "market_odds": "Y", "ev_percent": "+X%", "risk": "..." }},
        "recommendation": {{ "bet": "Tipp", "units": "X/10", "logic": "Begründung basierend auf dem Vergleich" }}
      }}
    ]
    WICHTIG: Wenn kein klares Signal durch Vergleich entsteht, gib eine leere Liste [] zurück.
    """

    models = ["gemini-flash-latest", "gemini-2.0-flash"]

    for model in models:
        try:
            time.sleep(2)
            response = client.models.generate_content(model=model, contents=prompt)
            if not response or not response.text: continue

            data = surgical_json_extraction(response.text)
            if data is not None: return data
        except Exception:
            continue
    return []

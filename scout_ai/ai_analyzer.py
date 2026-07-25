import os
import json
import time
import re
from typing import Any, Optional

from google import genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
client = None

if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
    except Exception as e:
        print(f"[AI][CRITICAL] Gemini-Initialisierung fehlgeschlagen: {type(e).__name__}: {e}")
else:
    print("[AI][CRITICAL] GEMINI_API_KEY fehlt. Keine Analyse möglich.")


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
    return cleaned


def surgical_json_extraction(text: str) -> Optional[list[dict[str, Any]]]:
    """Extrahiert robust eine JSON-Liste oder ein einzelnes JSON-Objekt."""
    if not text or not text.strip():
        return None

    cleaned = _strip_code_fences(text)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass

    list_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if list_match:
        try:
            parsed = json.loads(list_match.group(0))
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except json.JSONDecodeError as e:
            print(f"[AI][WARN] Eingebettete JSON-Liste ungültig: {e}")

    obj_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if obj_match:
        try:
            parsed = json.loads(obj_match.group(0))
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError as e:
            print(f"[AI][WARN] Eingebettetes JSON-Objekt ungültig: {e}")

    return None


def analyze_snippet(snippet: str, is_bundle: bool = False) -> list[dict[str, Any]]:
    if not client:
        print("[AI][ERROR] Gemini-Client nicht verfügbar.")
        return []

    current_time = time.strftime("%d.%m.%Y %H:%M")

    prompt = f"""
ROLE: Du bist der 'Strategic Head of Quant Analysis'.
MISSION: Vergleiche die folgenden verschiedenen Nachrichtenquellen und finde Übereinstimmungen oder versteckte Muster für Wett-Vorteile (+EV).

SYSTEM-ZEIT: {current_time}
INPUT-PAKET:
{snippet}

ANALYSE-AUFTRAG:
1. CROSS-REFERENCE: Suche nach demselben Spiel in verschiedenen Quellen.
2. PATTERN RECOGNITION: Wenn Quelle A eine Verletzung meldet und Quelle B einen Quotensturz, verbinde diese zu einem Signal.
3. CONFLICT CHECK: Wenn Quellen sich widersprechen, sei extrem vorsichtig und setze das Risiko hoch.
4. VALIDIERUNG: Berücksichtige nur Spiele in der Zukunft.
5. SIGNAL-STÄRKE: Akzeptiere auch ein einzelnes starkes Signal, wenn es konkrete, überprüfbare Informationen enthält. Kennzeichne dann den Grund klar und setze das Risiko konservativ.

AUSGABEFORMAT:
Antworte ausschließlich mit gültigem JSON. Keine Markdown-Codeblöcke, keine Einleitung und keine Erklärung außerhalb des JSON.

[
  {{
    "status": "ACCEPT",
    "reason": "Zusammenfassender Grund des Vergleichs",
    "match": "Team A vs Team B",
    "start_time": "Zeit",
    "sport": "Liga",
    "analysis": {{
      "fair_odds": "X",
      "market_odds": "Y",
      "ev_percent": "+X%",
      "risk": "LOW|MEDIUM|HIGH"
    }},
    "recommendation": {{
      "bet": "Tipp",
      "units": "X/10",
      "logic": "Begründung basierend auf den Quellen"
    }}
  }}
]

Wenn kein belastbares Signal existiert, antworte exakt mit [].
"""

    models = ["gemini-flash-latest", "gemini-2.0-flash"]

    for model in models:
        try:
            print(f"[AI] Versuche Modell: {model}")
            time.sleep(2)

            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )

            if not response:
                print(f"[AI][WARN] {model}: Keine Response erhalten.")
                continue

            raw_text = (response.text or "").strip()
            if not raw_text:
                print(f"[AI][WARN] {model}: Leerer Antworttext.")
                continue

            data = surgical_json_extraction(raw_text)
            if data is None:
                preview = raw_text[:1000].replace("\n", " ")
                print(f"[AI][ERROR] {model}: JSON-Extraktion fehlgeschlagen. Antwort: {preview}")
                continue

            if not data:
                print(f"[AI] {model}: Analyse erfolgreich, aber kein belastbares Signal gefunden.")
                return []

            accepted = [
                item
                for item in data
                if isinstance(item, dict) and item.get("status") == "ACCEPT"
            ]

            print(
                f"[AI] {model}: {len(data)} Ergebnis(se), "
                f"davon {len(accepted)} akzeptiert."
            )
            return data

        except Exception as e:
            print(f"[AI][ERROR] {model}: {type(e).__name__}: {e}")

    print("[AI][ERROR] Alle Gemini-Modelle sind fehlgeschlagen.")
    return []

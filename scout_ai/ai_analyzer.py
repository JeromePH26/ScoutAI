import json
import os
import re
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")
client = genai.Client(api_key=API_KEY) if API_KEY else None


def _strip_code_fences(text: str) -> str:
    cleaned = (text or "").strip()
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I).strip()


def surgical_json_extraction(text: str) -> Optional[list[dict[str, Any]]]:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        return None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", cleaned, re.S)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else None
        except json.JSONDecodeError:
            return None
    return None


def analyze_snippet(snippet: str, is_bundle: bool = False) -> list[dict[str, Any]]:
    if not client:
        print("[AI][ERROR] GEMINI_API_KEY fehlt oder Client ist nicht verfügbar.")
        return []

    prompt = f"""
ROLE: Quantitative Sports Intelligence Analyst.

INPUT:
{snippet}

AUFTRAG:
- Extrahiere nur Aussagen, die durch den Input gestützt werden.
- Prüfe, ob mehrere unabhängige Quellen dasselbe Ereignis bestätigen.
- Trenne bestätigte Fakten, plausible Inferenz und offene Unsicherheit.
- Erfinde keine Quoten, Wahrscheinlichkeiten, Fair Odds oder Expected Value.
- Ein Tipp ist nur ACTION, wenn der Input ein konkretes Match, einen konkreten Markt
  und eine nachvollziehbare Informationskante enthält.
- Ohne reale Marktquote darf status höchstens WATCH sein.
- Ein starkes offizielles Solo-Signal darf WATCH sein.
- Schwache allgemeine Predictions sind REJECT.

Antworte ausschließlich als JSON-Liste:
[
  {{
    "status": "ACTION|WATCH|REJECT",
    "signal_type": "CONSENSUS|OFFICIAL_SOLO|MARKET_MOVE|WEAK",
    "match": "Team A vs Team B oder UNKNOWN",
    "sport": "Sport/Liga oder UNKNOWN",
    "start_time": "ISO-Zeit oder UNKNOWN",
    "confidence": 0,
    "evidence": ["konkrete Evidenz"],
    "conflicts": ["Widersprüche"],
    "market": {{
      "bet": "konkreter Markt oder UNKNOWN",
      "market_odds": null,
      "model_probability": null,
      "expected_value": null,
      "requires_odds_validation": true
    }},
    "risk": "LOW|MEDIUM|HIGH",
    "reason": "kurze, überprüfbare Begründung"
  }}
]

Wenn keine verwertbare Intelligence existiert, antworte exakt mit [].
"""

    models = [PRIMARY_MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != PRIMARY_MODEL:
        models.append(FALLBACK_MODEL)

    for idx, model in enumerate(models):
        try:
            print(f"[AI] Quant-Analyse mit {model}")
            response = client.models.generate_content(model=model, contents=prompt)
            raw = (response.text or "").strip() if response else ""
            parsed = surgical_json_extraction(raw)
            if parsed is None:
                print(f"[AI][ERROR] {model}: Ungültiges JSON.")
                continue
            if not parsed:
                print(f"[AI] {model}: Kein verwertbares Signal.")
                return []  # Gültiges [] löst keinen teuren Fallback aus.

            for item in parsed:
                item["ai_model"] = model
            return parsed
        except Exception as exc:
            print(f"[AI][ERROR] {model}: {type(exc).__name__}: {exc}")
            # Fallback nur bei technischem Fehler.
            if idx == len(models) - 1:
                return []
    return []

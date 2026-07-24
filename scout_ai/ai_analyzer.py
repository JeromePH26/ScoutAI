import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

def analyze_snippet(snippet: str) -> dict:
    """
    Uses Gemini AI to extract structured data from a text snippet.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        return {}

    client = genai.Client(api_key=api_key)

    prompt = f"""
    Du bist die 'ScoutAI Multi-Sport Analysis Engine', ein hochpräziser Algorithmus für Sportwetten- und E-Sports-Prognosen.
    Analysiere den folgenden Text-Ausschnitt (Sportarten: Fußball, Basketball, Tennis, MMA, E-Sports wie CS2/LoL, US-Sports etc.) mit maximaler Genauigkeit.

    TEXT: "{snippet}"

    PROZESS-RICHTLINIEN:
    1. Extrahiere die Daten strikt nach dem unten stehenden JSON-Format.
    2. 'sport': Identifiziere die Sportart exakt (z.B. "Football", "Basketball", "E-Sports (CS2)", "Tennis", "MMA").
    3. 'confidence_score' (0-100%): Evaluiere die Stärke der Argumente. Berücksichtige bei E-Sports Faktoren wie Map-Vorteile, Roster-Changes oder Stand-ins.
    4. 'algo_reasoning': Eine professionelle, knappe Zusammenfassung (2-3 Sätze) der Entscheidungsgrundlage unter Einbeziehung sport-spezifischer Faktoren.
    5. MINIMAL-ANFORDERUNG: Wenn home_team, away_team oder recommended_bet nicht eindeutig identifizierbar sind ODER der confidence_score unter 75% liegt, gib EXAKT null zurück.
    6. 'odds': Extrahiere die Quote, falls erwähnt, sonst "N/A".

    JSON-FORMAT (AUSSCHLIESSLICH):
    {{
      "sport": "Name der Sportart",
      "home_team": "Team A / Spieler A",
      "away_team": "Team B / Spieler B",
      "league": "Liga / Turnier Name",
      "recommended_bet": "Konkreter Markt (z.B. O2.5, Handicap -1.5, Map 1 Winner)",
      "odds": "Quote (z.B. 1.85)",
      "confidence_score": 85,
      "consensus_factors": ["Faktor 1", "Faktor 2"],
      "algo_reasoning": "Sport-spezifische professionelle Begründung."
    }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt
        )

        # Extract JSON from response text
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        return json.loads(text)
    except Exception as e:
        print(f"AI Analysis failed: {e}")
        return {}

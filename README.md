# ScoutAI: Sportwetten-Konsens- & Sentiment-System

Dieses System scannt RSS-Feeds nach Sportwetten-Tipps, analysiert diese mit Google Gemini AI und sendet strukturierte Alarme per Telegram.

## Features
- **Smart Filtering:** Vorfilterung von RSS-Feeds nach relevanten Wett-Keywords.
- **AI Analysis:** Extraktion von Spielpaarung, Tipp und Konfidenz via Gemini 1.5 Flash.
- **Deduplizierung:** SQLite-Datenbank verhindert mehrfache Alarme für denselben Tipp.
- **Instant Alerts:** Telegram-Benachrichtigungen mit Markdown-Formatierung.

## Setup
1. Repository klonen oder Dateien kopieren.
2. Abhängigkeiten installieren:
   ```bash
   pip install -r requirements.txt
   ```
3. `.env.example` zu `.env` kopieren und API-Keys eintragen.
4. System starten:
   ```bash
   python scout_ai/main.py
   ```

## Projektstruktur
- `scout_ai/scraper.py`: RSS-Parsing & Text-Filterung.
- `scout_ai/ai_analyzer.py`: Gemini API Integration.
- `scout_ai/database.py`: SQLite Speicher.
- `scout_ai/notifier.py`: Telegram Bot Logik.
- `scout_ai/main.py`: Zentraler Orchestrator.

# ScoutAI Global Consensus v3

## Lage
Diese Version entfernt FootyStats vollständig. ScoutAI arbeitet stattdessen mit einem
kontrollierten weltweiten Quellennetz, RSS/Atom-Feeds und Google-News-RSS als Discovery-Layer.

## Pipeline
1. Quellenregister mit Tier, Kategorie, Qualitäts-Hinweis und Abrufintervall
2. höflicher Feed-Abruf pro Domain
3. ETag/Last-Modified-Caching
4. sofortiger Stopp bei HTTP 403/429
5. exakte Inhalts-Fingerprints gegen Kopien
6. lokales Clustering und mathematisches Ranking
7. Gemini nur für die besten Cluster
8. ACTION nur bei vorhandener echter Marktquote, sonst WATCH

## Installation
- `main.py`, `scraper.py`, `ai_analyzer.py`, `quant_engine.py` nach `scout_ai/` kopieren.
- `source_registry.py` neu hinzufügen.
- Variablen aus `.env.global.example` in Railway setzen.
- Bestehende `database.py` und `notifier.py` behalten.

## Wichtig
Google wird nur als Entdeckungsquelle genutzt. Die Software tarnt sich nicht,
umgeht keine Sperren, wechselt keine Proxys und versucht keine CAPTCHA-Umgehung.

## Nächster Ausbau
Nach 2–4 Wochen Messdaten:
- Quellen-Performance persistieren
- Syndication-Ursprung erkennen
- Liga-/Team-Entity-Resolver
- echte Odds-API
- Kalibrierung und Backtesting

"""
Nur als Einbaubeispiel verwenden, nicht blind deine bestehende main.py ersetzen.
"""

from scout_ai.entity_resolver import EntityType, build_default_resolver

resolver = build_default_resolver()


def enrich_article_with_entities(article: dict) -> dict:
    text = f"{article.get('title', '')}\n{article.get('summary', article.get('snippet', ''))}"
    matches = resolver.extract_from_text(text)

    article["entities"] = [
        {
            "entity_id": m.entity.entity_id,
            "canonical_name": m.entity.canonical_name,
            "entity_type": m.entity.entity_type.value,
            "sport": m.entity.sport,
            "league": m.entity.league,
            "confidence": m.confidence,
            "match_type": m.match_type,
        }
        for m in matches
    ]
    article["teams"] = [
        m.entity.canonical_name
        for m in matches
        if m.entity.entity_type == EntityType.TEAM
    ]
    article["players"] = [
        m.entity.canonical_name
        for m in matches
        if m.entity.entity_type == EntityType.PLAYER
    ]
    article["leagues"] = [
        m.entity.canonical_name
        for m in matches
        if m.entity.entity_type == EntityType.LEAGUE
    ]
    return article

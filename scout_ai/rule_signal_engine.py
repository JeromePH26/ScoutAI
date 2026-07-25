from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence


RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "POSTPONEMENT",
        (
            "postponed", "cancelled", "canceled", "abandoned",
            "verschoben", "abgesagt", "spielausfall",
        ),
    ),
    (
        "LINEUP",
        (
            "confirmed lineup", "starting lineup", "starting xi",
            "lineup confirmed", "aufstellung bestätigt", "bestaetigte aufstellung",
            "startelf", "starting eleven",
        ),
    ),
    (
        "SUSPENSION",
        (
            "suspended", "suspension", "ban confirmed",
            "gesperrt", "sperre", "rot gesperrt",
        ),
    ),
    (
        "INJURY",
        (
            "ruled out", "out injured", "injury", "injured", "doubtful",
            "questionable", "fitness test", "verletzung", "verletzt",
            "fällt aus", "faellt aus", "fraglich",
        ),
    ),
    (
        "MARKET_MOVE",
        (
            "odds shortened", "odds drift", "line movement", "market move",
            "unusual volume", "quote fällt", "quote faellt",
            "quote steigt", "quotenbewegung",
        ),
    ),
    (
        "WEATHER",
        (
            "weather warning", "heavy rain", "strong wind", "snow warning",
            "storm warning", "unwetterwarnung", "starkregen",
            "starker wind", "schneewarnung",
        ),
    ),
    (
        "ROTATION",
        (
            "rotation", "rotated squad", "rested players",
            "rotiert", "schont spieler", "kaderrotation",
        ),
    ),
    (
        "TEAM_NEWS",
        (
            "team news", "official statement", "official confirmation",
            "club statement", "confirmed", "vereinsmitteilung",
            "offiziell bestätigt", "offiziell bestaetigt",
        ),
    ),
)


@dataclass(frozen=True)
class RuleSignal:
    status: str
    signal_type: str
    event_cluster_id: str
    match: str
    sport: str
    league: str
    start_time: str
    confidence: int
    sources_supporting: int
    facts: tuple[str, ...]
    warnings: tuple[str, ...]
    risk: str
    reason: str

    def as_dict(self) -> dict[str, object]:
        facts = list(self.facts)
        warnings = list(self.warnings)
        return {
            "status": self.status,
            "signal_type": self.signal_type,
            "event_cluster_id": self.event_cluster_id,
            "match": self.match,
            "sport": self.sport,
            "league": self.league,
            "start_time": self.start_time,
            "confidence": self.confidence,
            "sources_supporting": self.sources_supporting,
            "facts": facts,
            "evidence": facts,
            "warnings": warnings,
            "conflicts": [
                warning for warning in warnings
                if "widerspr" in warning.lower() or "conflict" in warning.lower()
            ],
            "market": {
                "bet": f"INTELLIGENCE_{self.signal_type}",
                "market_odds": None,
                "model_probability": None,
                "fair_odds": None,
                "expected_value_percent": None,
                "requires_odds_validation": True,
            },
            "analysis": {
                "fair_odds": "Nicht berechnet",
                "ev_percent": "Nicht berechnet",
                "risk": self.risk,
            },
            "recommendation": {
                "bet": "NO BET – manuell prüfen",
                "units": 0,
                "logic": self.reason,
            },
            "risk": self.risk,
            "reason": self.reason,
        }


def build_rule_signals(cluster: object, decision: object) -> list[dict[str, object]]:
    """
    Create deterministic sports-intelligence WATCH signals.

    This module deliberately never creates ACTION. It has no odds model and
    therefore cannot calculate fair odds or expected value.
    """

    decision_name = str(_value(decision, "decision", "SKIP") or "SKIP").upper()
    if decision_name != "ANALYZE":
        return []

    articles = _articles(cluster)
    if not articles:
        return []

    teams = _team_names(cluster, articles)
    if len(teams) < 2:
        return []

    signal_type, matched_terms = _detect_signal_type(articles)
    if signal_type == "CONSENSUS" and not matched_terms:
        # A generic news cluster without a concrete event is not useful enough.
        return []

    confidence = int(_value(decision, "confidence", 0) or 0)
    independent_sources = int(_value(decision, "independent_sources", 0) or 0)
    if independent_sources < 2:
        return []

    facts = _evidence_facts(articles, matched_terms)
    if not facts:
        return []

    warnings = tuple(str(x) for x in (_value(decision, "warnings", ()) or ()))
    reasons = tuple(str(x) for x in (_value(decision, "reasons", ()) or ()))
    risk = _risk_level(decision, warnings)

    match = f"{teams[0]} vs {teams[1]}"
    sport, league = _sport_and_league(cluster, articles)
    reason = _build_reason(
        signal_type=signal_type,
        confidence=confidence,
        independent_sources=independent_sources,
        facts=facts,
        reasons=reasons,
        warnings=warnings,
    )

    signal = RuleSignal(
        status="WATCH",
        signal_type=signal_type,
        event_cluster_id=str(_value(decision, "cluster_id", "") or ""),
        match=match,
        sport=sport,
        league=league,
        start_time="UNKNOWN",
        confidence=max(0, min(100, confidence)),
        sources_supporting=independent_sources,
        facts=tuple(facts[:5]),
        warnings=warnings[:5],
        risk=risk,
        reason=reason,
    )
    return [signal.as_dict()]


def _detect_signal_type(
    articles: Sequence[Mapping[str, object]],
) -> tuple[str, tuple[str, ...]]:
    text = _normal(" ".join(_article_text(article) for article in articles))
    for signal_type, terms in RULES:
        matches = tuple(term for term in terms if _normal(term) in text)
        if matches:
            return signal_type, matches
    return "CONSENSUS", ()


def _evidence_facts(
    articles: Sequence[Mapping[str, object]],
    matched_terms: Sequence[str],
) -> list[str]:
    facts: list[str] = []
    normalized_terms = tuple(_normal(term) for term in matched_terms)

    for article in articles:
        title = re.sub(r"\s+", " ", str(article.get("title") or "")).strip()
        snippet = re.sub(r"\s+", " ", str(article.get("snippet") or "")).strip()
        combined = _normal(f"{title} {snippet}")

        if normalized_terms and not any(term in combined for term in normalized_terms):
            continue

        source = str(article.get("source") or "Unbekannte Quelle").strip()
        statement = title or snippet[:220]
        if not statement:
            continue
        fact = f"{source}: {statement[:260]}"
        if fact not in facts:
            facts.append(fact)

    return facts


def _build_reason(
    *,
    signal_type: str,
    confidence: int,
    independent_sources: int,
    facts: Sequence[str],
    reasons: Sequence[str],
    warnings: Sequence[str],
) -> str:
    event_labels = {
        "POSTPONEMENT": "mögliche Spielverschiebung oder Absage",
        "LINEUP": "relevante Aufstellungsinformation",
        "SUSPENSION": "relevante Sperrenmeldung",
        "INJURY": "relevante Verletzungs- oder Fitnessmeldung",
        "MARKET_MOVE": "auffällige Quoten- oder Marktbewegung",
        "WEATHER": "möglicherweise spielrelevante Wetterlage",
        "ROTATION": "mögliche Rotation oder Schonung",
        "TEAM_NEWS": "bestätigte Teamnachricht",
        "CONSENSUS": "bestätigtes Sportereignis",
    }
    label = event_labels.get(signal_type, "relevante Sportmeldung")

    parts = [
        f"ScoutAI erkennt eine {label}.",
        f"Die Meldung wird von {independent_sources} unabhängigen Quellen gestützt.",
        f"Der regelbasierte Consensus-Score beträgt {confidence}/100.",
    ]
    if facts:
        parts.append(f"Konkrete Belege: {len(facts)}.")
    if reasons:
        parts.append("Stärken: " + "; ".join(reasons[:3]) + ".")
    if warnings:
        parts.append("Offene Punkte: " + "; ".join(warnings[:3]) + ".")
    parts.append(
        "Es wurde keine faire Quote und kein Expected Value berechnet; "
        "das Signal ist daher nur WATCH und keine Wettfreigabe."
    )
    return " ".join(parts)


def _risk_level(decision: object, warnings: Sequence[str]) -> str:
    conflict_penalty = float(_value(decision, "conflict_penalty", 0.0) or 0.0)
    quality = float(_value(decision, "source_quality", 0.0) or 0.0)
    lowered = " ".join(warnings).lower()

    if conflict_penalty >= 0.18 or "widerspr" in lowered or quality < 0.55:
        return "HIGH"
    if conflict_penalty > 0 or quality < 0.78 or warnings:
        return "MEDIUM"
    return "LOW"


def _team_names(
    cluster: object,
    articles: Sequence[Mapping[str, object]],
) -> list[str]:
    names: list[str] = []
    for article in articles:
        for entity in article.get("entities", []) or []:
            if not isinstance(entity, Mapping):
                continue
            if str(entity.get("entity_type") or "") != "team":
                continue
            name = str(entity.get("canonical_name") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _sport_and_league(
    cluster: object,
    articles: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    sports: list[str] = []
    leagues: list[str] = []

    for article in articles:
        for entity in article.get("entities", []) or []:
            if not isinstance(entity, Mapping):
                continue
            sport = str(entity.get("sport") or "").strip()
            if sport and sport not in sports:
                sports.append(sport)

            entity_type = str(entity.get("entity_type") or "")
            if entity_type in {"league", "competition"}:
                league = str(entity.get("canonical_name") or "").strip()
            else:
                league = str(entity.get("league") or "").strip()
            if league and league not in leagues:
                leagues.append(league)

    return (
        sports[0] if sports else "UNKNOWN",
        leagues[0] if leagues else "UNKNOWN",
    )


def _articles(cluster: object) -> list[dict]:
    value = _value(cluster, "articles", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _article_text(article: Mapping[str, object]) -> str:
    return " ".join(
        str(article.get(key) or "")
        for key in ("title", "summary", "snippet", "description")
    )


def _value(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _normal(value: str) -> str:
    value = (value or "").casefold()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

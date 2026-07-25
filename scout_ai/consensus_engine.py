from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence


TIER_QUALITY = {
    "A": 0.88,
    "B": 0.72,
    "C": 0.56,
    "D": 0.38,
}

SOURCE_MARKERS = {
    "official": 0.98,
    "reuters": 0.94,
    "associated press": 0.92,
    "ap sports": 0.92,
    "bbc": 0.92,
    "espn": 0.88,
    "sky sports": 0.86,
    "guardian": 0.84,
    "opta": 0.88,
    "statsbomb": 0.88,
    "hltv": 0.78,
    "betfair": 0.72,
    "oddschecker": 0.70,
    "reddit": 0.38,
}

EVIDENCE_TERMS = {
    "official": 1.00,
    "confirmed": 0.96,
    "ruled out": 0.95,
    "confirmed lineup": 0.98,
    "starting lineup": 0.94,
    "suspended": 0.90,
    "late change": 0.88,
    "odds shortened": 0.86,
    "line movement": 0.84,
    "unusual volume": 0.82,
    "injury": 0.76,
    "doubtful": 0.70,
    "questionable": 0.62,
    "rotation": 0.60,
    "weather warning": 0.68,
    "heavy rain": 0.62,
    "strong wind": 0.62,
}

NOISE_TERMS = {
    "rumour": 0.28,
    "rumor": 0.28,
    "opinion": 0.20,
    "prediction": 0.16,
    "preview": 0.12,
    "best bets": 0.10,
    "tips today": 0.10,
}

CONFLICT_PAIRS = (
    ("ruled out", "available"),
    ("out injured", "fit to play"),
    ("suspended", "cleared"),
    ("confirmed", "unconfirmed"),
    ("postponed", "goes ahead"),
    ("starting lineup", "benched"),
)


@dataclass(frozen=True)
class ConsensusDecision:
    cluster_id: str
    decision: str
    confidence: int
    article_count: int
    independent_sources: int
    official_sources: int
    source_quality: float
    corroboration: float
    evidence_strength: float
    freshness: float
    entity_completeness: float
    source_diversity: float
    conflict_penalty: float
    syndication_penalty: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready_for_ai(self) -> bool:
        return self.decision == "ANALYZE"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_cluster(
    cluster: object,
    *,
    now: datetime | None = None,
    analyze_threshold: int | None = None,
    watch_threshold: int | None = None,
    min_independent_sources: int | None = None,
) -> ConsensusDecision:
    """Score an EventCluster without making a betting decision."""

    now = _utc(now or datetime.now(timezone.utc))
    analyze_threshold = analyze_threshold or int(
        os.getenv("CONSENSUS_ANALYZE_MIN", "64")
    )
    watch_threshold = watch_threshold or int(
        os.getenv("CONSENSUS_WATCH_MIN", "38")
    )
    min_independent_sources = min_independent_sources or int(
        os.getenv("CONSENSUS_MIN_SOURCES", "2")
    )

    if not 0 <= watch_threshold <= analyze_threshold <= 100:
        raise ValueError("thresholds must satisfy 0 <= watch <= analyze <= 100")
    if min_independent_sources < 1:
        raise ValueError("min_independent_sources must be at least 1")

    articles = _articles(cluster)
    cluster_id = str(_value(cluster, "cluster_id", "") or _fallback_cluster_id(articles))
    sources = {_source_key(article) for article in articles if _source_key(article)}
    categories = {
        _normal(str(article.get("source_category") or "unknown"))
        for article in articles
    }
    independent_sources = len(sources)
    official_sources = sum(1 for article in articles if _is_official(article))

    qualities = [_article_quality(article) for article in articles]
    source_quality = _quality_score(qualities)
    corroboration = _corroboration(independent_sources)
    evidence_strength = _evidence_strength(articles)
    freshness = _freshness(articles, now)
    entity_completeness = _entity_completeness(cluster, articles)
    source_diversity = _source_diversity(independent_sources, categories)
    conflict_penalty = _conflict_penalty(articles)
    syndication_penalty = _syndication_penalty(articles)

    raw = (
        0.24 * source_quality
        + 0.22 * corroboration
        + 0.19 * evidence_strength
        + 0.12 * freshness
        + 0.11 * entity_completeness
        + 0.12 * source_diversity
        - 0.35 * conflict_penalty
        - 0.18 * syndication_penalty
    )
    raw = max(0.0, min(1.0, raw))
    confidence = round(raw * 100)

    analyze_allowed = (
        independent_sources >= min_independent_sources
        and entity_completeness >= 0.55
        and conflict_penalty < 0.18
    )

    if confidence >= analyze_threshold and analyze_allowed:
        decision = "ANALYZE"
    elif confidence >= watch_threshold:
        decision = "WATCH"
    else:
        decision = "SKIP"

    reasons: list[str] = []
    warnings: list[str] = []

    if independent_sources >= min_independent_sources:
        reasons.append(f"{independent_sources} unabhängige Quellen")
    elif independent_sources == 1:
        warnings.append("Nur eine unabhängige Quelle")
    else:
        warnings.append("Keine eindeutige Quelle")

    if source_quality >= 0.85:
        reasons.append("Hohe Quellenqualität")
    elif source_quality < 0.55:
        warnings.append("Niedrige Quellenqualität")

    if evidence_strength >= 0.65:
        reasons.append("Konkrete Ereignis-Evidenz")
    elif evidence_strength < 0.25:
        warnings.append("Kaum konkrete Ereignis-Evidenz")

    if entity_completeness >= 0.95:
        reasons.append("Beide Teams eindeutig erkannt")
    elif entity_completeness < 0.55:
        warnings.append("Spielidentität nicht vollständig aufgelöst")

    if freshness >= 0.75:
        reasons.append("Aktuelle Meldungen")
    elif freshness < 0.40:
        warnings.append("Meldungen sind möglicherweise veraltet")

    if official_sources:
        reasons.append(f"{official_sources} offizielle Quelle(n)")

    if conflict_penalty >= 0.18:
        warnings.append("Widersprüchliche Meldungen erkannt")
    elif conflict_penalty > 0:
        warnings.append("Leichte Widersprüche erkannt")

    if syndication_penalty >= 0.15:
        warnings.append("Mehrere Meldungen wirken syndiziert oder nahezu identisch")

    if decision == "ANALYZE":
        reasons.append("Cluster für KI-Analyse freigegeben")
    elif decision == "WATCH":
        warnings.append("Noch keine vollständige Freigabe für die KI-Analyse")
    else:
        warnings.append("Cluster wird vorerst übersprungen")

    return ConsensusDecision(
        cluster_id=cluster_id,
        decision=decision,
        confidence=confidence,
        article_count=len(articles),
        independent_sources=independent_sources,
        official_sources=official_sources,
        source_quality=round(source_quality, 4),
        corroboration=round(corroboration, 4),
        evidence_strength=round(evidence_strength, 4),
        freshness=round(freshness, 4),
        entity_completeness=round(entity_completeness, 4),
        source_diversity=round(source_diversity, 4),
        conflict_penalty=round(conflict_penalty, 4),
        syndication_penalty=round(syndication_penalty, 4),
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def rank_consensus(
    clusters: Iterable[object],
    *,
    now: datetime | None = None,
) -> list[tuple[object, ConsensusDecision]]:
    scored = [(cluster, evaluate_cluster(cluster, now=now)) for cluster in clusters]
    return sorted(
        scored,
        key=lambda item: (
            item[1].decision == "ANALYZE",
            item[1].confidence,
            item[1].independent_sources,
            item[1].article_count,
        ),
        reverse=True,
    )


def build_consensus_bundle(
    cluster: object,
    decision: ConsensusDecision,
    *,
    max_articles: int = 8,
) -> str:
    """Create the audited bundle that is later sent to Gemini."""

    if max_articles <= 0:
        raise ValueError("max_articles must be positive")

    articles = _articles(cluster)
    team_ids = sorted(_team_entity_ids(cluster, articles))
    league_ids = sorted(_league_entity_ids(cluster, articles))

    lines = [
        f"EVENT_CLUSTER_ID={decision.cluster_id}",
        f"CONSENSUS_DECISION={decision.decision}",
        f"CONSENSUS_CONFIDENCE={decision.confidence}",
        f"ARTICLE_COUNT={decision.article_count}",
        f"INDEPENDENT_SOURCES={decision.independent_sources}",
        f"OFFICIAL_SOURCES={decision.official_sources}",
        f"SOURCE_QUALITY={decision.source_quality}",
        f"CORROBORATION={decision.corroboration}",
        f"EVIDENCE_STRENGTH={decision.evidence_strength}",
        f"FRESHNESS={decision.freshness}",
        f"ENTITY_COMPLETENESS={decision.entity_completeness}",
        f"SOURCE_DIVERSITY={decision.source_diversity}",
        f"CONFLICT_PENALTY={decision.conflict_penalty}",
        f"SYNDICATION_PENALTY={decision.syndication_penalty}",
        f"TEAM_ENTITY_IDS={','.join(team_ids) or 'UNKNOWN'}",
        f"LEAGUE_ENTITY_IDS={','.join(league_ids) or 'UNKNOWN'}",
        f"REASONS={' | '.join(decision.reasons) or 'NONE'}",
        f"WARNINGS={' | '.join(decision.warnings) or 'NONE'}",
        "POLICY=This score only authorizes AI review. It never authorizes a bet.",
    ]

    for index, article in enumerate(articles[:max_articles], start=1):
        snippet = re.sub(r"\s+", " ", str(article.get("snippet") or ""))[:1200]
        lines.extend(
            [
                "",
                f"SOURCE_{index}={article.get('source') or 'UNKNOWN'}",
                f"SOURCE_TIER_{index}={article.get('source_tier') or 'UNKNOWN'}",
                f"SOURCE_QUALITY_HINT_{index}={article.get('source_quality_hint')}",
                f"TITLE_{index}={article.get('title') or 'UNKNOWN'}",
                f"PUBLISHED_AT_{index}={article.get('published_at') or 'UNKNOWN'}",
                f"URL_{index}={article.get('link') or 'UNKNOWN'}",
                f"TEXT_{index}={snippet}",
            ]
        )

    return "\n".join(lines)


def _articles(cluster: object) -> list[dict]:
    value = _value(cluster, "articles", [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _value(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _normal(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _source_key(article: Mapping[str, object]) -> str:
    source = _normal(str(article.get("source") or ""))
    if source:
        return source
    link = str(article.get("link") or "")
    match = re.match(r"https?://([^/]+)", link, flags=re.I)
    return _normal(match.group(1)) if match else ""


def _article_quality(article: Mapping[str, object]) -> float:
    hint = article.get("source_quality_hint")
    try:
        value = float(hint)
        if 0 <= value <= 1:
            return value
    except (TypeError, ValueError):
        pass

    tier = str(article.get("source_tier") or "").upper()
    if tier in TIER_QUALITY:
        return TIER_QUALITY[tier]

    source = _source_key(article)
    for marker, quality in SOURCE_MARKERS.items():
        if marker in source:
            return quality
    return 0.58


def _quality_score(qualities: Sequence[float]) -> float:
    if not qualities:
        return 0.0
    return 0.65 * max(qualities) + 0.35 * (sum(qualities) / len(qualities))


def _is_official(article: Mapping[str, object]) -> bool:
    category = _normal(str(article.get("source_category") or ""))
    source = _source_key(article)
    return category == "official" or any(
        marker in source
        for marker in ("official", "club website", "federation", "league office")
    )


def _corroboration(independent_sources: int) -> float:
    if independent_sources <= 1:
        return 0.0
    return 1.0 - math.exp(-0.85 * (independent_sources - 1))


def _article_evidence(article: Mapping[str, object]) -> float:
    text = _normal(f"{article.get('title') or ''} {article.get('snippet') or ''}")
    positive = sum(weight for term, weight in EVIDENCE_TERMS.items() if term in text)
    noise = sum(weight for term, weight in NOISE_TERMS.items() if term in text)
    score = 1.0 - math.exp(-positive / 1.45)
    return max(0.0, min(1.0, score - noise))


def _evidence_strength(articles: Sequence[Mapping[str, object]]) -> float:
    if not articles:
        return 0.0
    scores = [_article_evidence(article) for article in articles]
    return 0.60 * max(scores) + 0.40 * (sum(scores) / len(scores))


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return _utc(parsed)
    except (TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _freshness(articles: Sequence[Mapping[str, object]], now: datetime) -> float:
    if not articles:
        return 0.0

    values: list[float] = []
    for article in articles:
        published = _parse_time(article.get("published_at"))
        if published is None:
            values.append(0.55)
            continue
        age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
        values.append(max(0.08, math.exp(-math.log(2) * age_hours / 18.0)))

    return 0.55 * max(values) + 0.45 * (sum(values) / len(values))


def _entity_rows(articles: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    for article in articles:
        for row in article.get("entities", []) or []:
            if isinstance(row, Mapping):
                rows.append(row)
    return rows


def _team_entity_ids(
    cluster: object,
    articles: Sequence[Mapping[str, object]],
) -> set[str]:
    existing = _value(cluster, "team_entity_ids", set())
    result = {str(value) for value in existing or [] if str(value)}
    for row in _entity_rows(articles):
        if row.get("entity_type") == "team" and row.get("entity_id"):
            result.add(str(row["entity_id"]))
    return result


def _league_entity_ids(
    cluster: object,
    articles: Sequence[Mapping[str, object]],
) -> set[str]:
    existing = _value(cluster, "league_entity_ids", set())
    result = {str(value) for value in existing or [] if str(value)}
    for row in _entity_rows(articles):
        if row.get("entity_type") == "league" and row.get("entity_id"):
            result.add(str(row["entity_id"]))
    return result


def _entity_completeness(
    cluster: object,
    articles: Sequence[Mapping[str, object]],
) -> float:
    team_ids = _team_entity_ids(cluster, articles)
    league_ids = _league_entity_ids(cluster, articles)
    all_entities = {
        str(row.get("entity_id"))
        for row in _entity_rows(articles)
        if row.get("entity_id")
    }

    if len(team_ids) >= 2:
        return 1.0
    if len(team_ids) == 1 and league_ids:
        return 0.68
    if len(team_ids) == 1:
        return 0.58
    if league_ids or all_entities:
        return 0.34
    return 0.12


def _source_diversity(
    independent_sources: int,
    categories: set[str],
) -> float:
    source_part = min(1.0, independent_sources / 3.0)
    category_part = min(1.0, len({c for c in categories if c}) / 3.0)
    return 0.68 * source_part + 0.32 * category_part


def _conflict_penalty(articles: Sequence[Mapping[str, object]]) -> float:
    texts = [
        (_source_key(article), _normal(f"{article.get('title') or ''} {article.get('snippet') or ''}"))
        for article in articles
    ]
    penalty = 0.0
    for left, right in CONFLICT_PAIRS:
        left_sources = {source for source, text in texts if left in text}
        right_sources = {source for source, text in texts if right in text}
        if left_sources and right_sources and left_sources != right_sources:
            penalty += 0.18
    return min(0.45, penalty)


def _title_tokens(article: Mapping[str, object]) -> set[str]:
    return {
        token
        for token in _normal(str(article.get("title") or "")).split()
        if len(token) >= 3
    }


def _syndication_penalty(articles: Sequence[Mapping[str, object]]) -> float:
    if len(articles) < 2:
        return 0.0

    pairs = 0
    near_duplicates = 0
    for index, left in enumerate(articles):
        left_tokens = _title_tokens(left)
        for right in articles[index + 1 :]:
            right_tokens = _title_tokens(right)
            if not left_tokens or not right_tokens:
                continue
            pairs += 1
            similarity = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
            if similarity >= 0.86:
                near_duplicates += 1

    if pairs == 0:
        return 0.0
    return min(0.30, 0.30 * (near_duplicates / pairs))


def _fallback_cluster_id(articles: Sequence[Mapping[str, object]]) -> str:
    identity = "|".join(
        sorted(_normal(str(article.get("title") or "")) for article in articles)
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"event_{digest}"

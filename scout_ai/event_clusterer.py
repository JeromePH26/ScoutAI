from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

try:
    from scout_ai.entity_resolver import (
        EntityResolver,
        EntityType,
        build_default_resolver,
        normalize_text,
    )
except ImportError:
    from entity_resolver import (
        EntityResolver,
        EntityType,
        build_default_resolver,
        normalize_text,
    )


STOPWORDS = {
    "about", "after", "against", "ahead", "also", "and", "are", "auf", "aus",
    "bei", "best", "bet", "bets", "das", "dem", "den", "der", "die", "ein",
    "eine", "einer", "for", "from", "gegen", "heute", "im", "in", "ist", "latest",
    "mit", "news", "oder", "of", "on", "prediction", "preview", "that", "the", "this",
    "today", "und", "von", "vor", "vs", "with", "zum", "zur",
}


@dataclass
class EventCluster:
    """A group of articles that most likely describe the same sports event."""

    cluster_id: str
    articles: list[dict] = field(default_factory=list)
    entity_ids: set[str] = field(default_factory=set)
    team_entity_ids: set[str] = field(default_factory=set)
    league_entity_ids: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    first_seen: str | None = None
    last_seen: str | None = None

    @property
    def article_count(self) -> int:
        return len(self.articles)

    @property
    def independent_sources(self) -> int:
        return len(self.sources)

    @property
    def primary_title(self) -> str:
        if not self.articles:
            return "UNKNOWN"
        return str(self.articles[0].get("title") or "UNKNOWN")

    def add(self, article: Mapping[str, object]) -> None:
        item = dict(article)
        self.articles.append(item)
        self.entity_ids.update(_entity_ids(item))
        self.team_entity_ids.update(_entity_ids(item, EntityType.TEAM.value))
        self.league_entity_ids.update(_entity_ids(item, EntityType.LEAGUE.value))

        source = _source_key(item)
        if source:
            self.sources.add(source)

        published_at = _published_at(item)
        if published_at:
            value = published_at.isoformat()
            if self.first_seen is None or value < self.first_seen:
                self.first_seen = value
            if self.last_seen is None or value > self.last_seen:
                self.last_seen = value

    def refresh_cluster_id(self) -> None:
        self.cluster_id = _cluster_id(self.articles)

    def as_dict(self, *, include_articles: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "cluster_id": self.cluster_id,
            "primary_title": self.primary_title,
            "article_count": self.article_count,
            "independent_sources": self.independent_sources,
            "entity_ids": sorted(self.entity_ids),
            "team_entity_ids": sorted(self.team_entity_ids),
            "league_entity_ids": sorted(self.league_entity_ids),
            "sources": sorted(self.sources),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }
        if include_articles:
            payload["articles"] = self.articles
        return payload


def enrich_article_with_entities(
    article: Mapping[str, object],
    resolver: EntityResolver | None = None,
) -> dict:
    """Return a copy of an article with normalized entity metadata attached."""

    resolver = resolver or build_default_resolver()
    enriched = dict(article)
    text = _article_text(enriched)
    matches = resolver.extract_from_text(text)

    merged: dict[str, dict[str, object]] = {}
    for existing in enriched.get("entities", []) or []:
        if not isinstance(existing, Mapping):
            continue
        entity_id = str(existing.get("entity_id") or "").strip()
        if entity_id:
            merged[entity_id] = dict(existing)

    for match in matches:
        merged[match.entity.entity_id] = {
            "entity_id": match.entity.entity_id,
            "canonical_name": match.entity.canonical_name,
            "entity_type": match.entity.entity_type.value,
            "sport": match.entity.sport,
            "country": match.entity.country,
            "league": match.entity.league,
            "confidence": match.confidence,
            "match_type": match.match_type,
        }

    entities = sorted(
        merged.values(),
        key=lambda row: (
            str(row.get("entity_type") or ""),
            str(row.get("canonical_name") or ""),
        ),
    )
    enriched["entities"] = entities
    enriched["entity_ids"] = [str(row["entity_id"]) for row in entities]
    enriched["teams"] = [
        str(row.get("canonical_name") or "")
        for row in entities
        if row.get("entity_type") == EntityType.TEAM.value
    ]
    enriched["team_entity_ids"] = [
        str(row["entity_id"])
        for row in entities
        if row.get("entity_type") == EntityType.TEAM.value
    ]
    enriched["leagues"] = [
        str(row.get("canonical_name") or "")
        for row in entities
        if row.get("entity_type") == EntityType.LEAGUE.value
    ]
    enriched["players"] = [
        str(row.get("canonical_name") or "")
        for row in entities
        if row.get("entity_type") == EntityType.PLAYER.value
    ]
    return enriched


def article_similarity(
    left: Mapping[str, object],
    right: Mapping[str, object],
    *,
    max_time_gap_hours: float = 72.0,
) -> float:
    """Return a conservative 0..1 score for whether two articles describe one event."""

    if not _within_time_window(left, right, max_time_gap_hours):
        return 0.0

    left_teams = _entity_ids(left, EntityType.TEAM.value)
    right_teams = _entity_ids(right, EntityType.TEAM.value)
    left_entities = _entity_ids(left)
    right_entities = _entity_ids(right)

    team_score = _jaccard(left_teams, right_teams)
    entity_score = _jaccard(left_entities, right_entities)
    token_score = _jaccard(_article_tokens(left), _article_tokens(right))

    if left_teams and right_teams:
        if left_teams.isdisjoint(right_teams):
            return min(0.34, 0.15 * entity_score + 0.19 * token_score)

        score = 0.58 * team_score + 0.24 * entity_score + 0.18 * token_score
        if left_teams == right_teams and len(left_teams) >= 2:
            score += 0.14
        return min(1.0, score)

    if left_entities and right_entities:
        return min(1.0, 0.62 * entity_score + 0.38 * token_score)

    return token_score


def cluster_events(
    articles: Iterable[Mapping[str, object]],
    *,
    resolver: EntityResolver | None = None,
    similarity_threshold: float = 0.52,
    max_time_gap_hours: float = 72.0,
) -> list[EventCluster]:
    """Enrich, deduplicate and cluster sports articles by event identity."""

    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between 0 and 1")
    if max_time_gap_hours <= 0:
        raise ValueError("max_time_gap_hours must be positive")

    resolver = resolver or build_default_resolver()
    prepared = _deduplicate(
        enrich_article_with_entities(article, resolver) for article in articles
    )
    prepared.sort(key=_sort_key)

    clusters: list[EventCluster] = []
    for article in prepared:
        best_cluster: EventCluster | None = None
        best_score = 0.0

        for cluster in clusters:
            score = max(
                (
                    article_similarity(
                        article,
                        member,
                        max_time_gap_hours=max_time_gap_hours,
                    )
                    for member in cluster.articles[-8:]
                ),
                default=0.0,
            )
            if score > best_score:
                best_cluster = cluster
                best_score = score

        if best_cluster is not None and best_score >= similarity_threshold:
            best_cluster.add(article)
            best_cluster.refresh_cluster_id()
        else:
            cluster = EventCluster(cluster_id="")
            cluster.add(article)
            cluster.refresh_cluster_id()
            clusters.append(cluster)

    return sorted(
        clusters,
        key=lambda cluster: (
            cluster.article_count,
            cluster.independent_sources,
            cluster.last_seen or "",
        ),
        reverse=True,
    )


def build_event_bundle(cluster: EventCluster, max_articles: int = 8) -> str:
    """Build a compact, deterministic text bundle for the later consensus engine."""

    if max_articles <= 0:
        raise ValueError("max_articles must be positive")

    lines = [
        f"EVENT_CLUSTER_ID={cluster.cluster_id}",
        f"ARTICLE_COUNT={cluster.article_count}",
        f"INDEPENDENT_SOURCES={cluster.independent_sources}",
        f"TEAM_ENTITY_IDS={','.join(sorted(cluster.team_entity_ids)) or 'UNKNOWN'}",
        f"LEAGUE_ENTITY_IDS={','.join(sorted(cluster.league_entity_ids)) or 'UNKNOWN'}",
    ]
    for index, article in enumerate(cluster.articles[:max_articles], start=1):
        snippet = re.sub(r"\s+", " ", str(article.get("snippet") or ""))[:1200]
        lines.extend(
            [
                "",
                f"SOURCE_{index}={article.get('source') or 'UNKNOWN'}",
                f"TITLE_{index}={article.get('title') or 'UNKNOWN'}",
                f"PUBLISHED_AT_{index}={article.get('published_at') or 'UNKNOWN'}",
                f"URL_{index}={article.get('link') or 'UNKNOWN'}",
                f"TEXT_{index}={snippet}",
            ]
        )
    return "\n".join(lines)


def _article_text(article: Mapping[str, object]) -> str:
    return "\n".join(
        str(article.get(key) or "")
        for key in ("title", "summary", "snippet", "description")
    )


def _entity_ids(article: Mapping[str, object], entity_type: str | None = None) -> set[str]:
    result: set[str] = set()
    for row in article.get("entities", []) or []:
        if not isinstance(row, Mapping):
            continue
        if entity_type is not None and str(row.get("entity_type")) != entity_type:
            continue
        entity_id = str(row.get("entity_id") or "").strip()
        if entity_id:
            result.add(entity_id)
    return result


def _article_tokens(article: Mapping[str, object]) -> set[str]:
    normalized = normalize_text(
        f"{article.get('title') or ''} {article.get('snippet') or ''}"
    )
    return {
        token
        for token in normalized.split()
        if len(token) >= 3 and token not in STOPWORDS and not token.isdigit()
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _published_at(article: Mapping[str, object]) -> datetime | None:
    value = article.get("published_at")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _within_time_window(
    left: Mapping[str, object],
    right: Mapping[str, object],
    max_time_gap_hours: float,
) -> bool:
    left_time = _published_at(left)
    right_time = _published_at(right)
    if left_time is None or right_time is None:
        return True
    gap = abs((left_time - right_time).total_seconds()) / 3600.0
    return gap <= max_time_gap_hours


def _source_key(article: Mapping[str, object]) -> str:
    source = str(article.get("source") or "").strip()
    if source:
        return normalize_text(source)
    link = str(article.get("link") or "").strip()
    match = re.match(r"https?://([^/]+)", link, flags=re.I)
    return normalize_text(match.group(1)) if match else ""


def _content_key(article: Mapping[str, object]) -> str:
    existing = str(article.get("content_fingerprint") or "").strip()
    if existing:
        return existing
    payload = "|".join(
        normalize_text(str(article.get(key) or ""))
        for key in ("title", "link", "snippet")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _deduplicate(articles: Iterable[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for article in articles:
        key = _content_key(article)
        current = unique.get(key)
        if current is None or len(str(article.get("snippet") or "")) > len(
            str(current.get("snippet") or "")
        ):
            unique[key] = article
    return list(unique.values())


def _cluster_id(articles: Sequence[Mapping[str, object]]) -> str:
    team_ids: set[str] = set()
    league_ids: set[str] = set()
    entity_ids: set[str] = set()
    tokens: set[str] = set()

    for article in articles:
        team_ids.update(_entity_ids(article, EntityType.TEAM.value))
        league_ids.update(_entity_ids(article, EntityType.LEAGUE.value))
        entity_ids.update(_entity_ids(article))
        tokens.update(_article_tokens(article))

    if team_ids:
        identity = "teams|" + "|".join(sorted(team_ids))
        if league_ids:
            identity += "|leagues|" + "|".join(sorted(league_ids))
    elif entity_ids:
        identity = "entities|" + "|".join(sorted(entity_ids))
    else:
        identity = "tokens|" + "|".join(sorted(tokens)[:20])

    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"event_{digest}"


def _sort_key(article: Mapping[str, object]) -> tuple[int, str]:
    published = _published_at(article)
    if published is None:
        return (1, str(article.get("title") or ""))
    return (0, published.isoformat())

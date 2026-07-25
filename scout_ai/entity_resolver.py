from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence


class EntityType(str, Enum):
    TEAM = "team"
    PLAYER = "player"
    LEAGUE = "league"
    COMPETITION = "competition"
    COACH = "coach"
    VENUE = "venue"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Entity:
    entity_id: str
    canonical_name: str
    entity_type: EntityType = EntityType.UNKNOWN
    sport: str | None = None
    country: str | None = None
    league: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EntityMatch:
    entity: Entity
    matched_text: str
    normalized_text: str
    confidence: float
    match_type: str


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"['’`´]", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    return normalize_text(value).replace(" ", "_") or "unknown"


def stable_entity_id(
    canonical_name: str,
    entity_type: EntityType | str = EntityType.UNKNOWN,
    sport: str | None = None,
    country: str | None = None,
) -> str:
    type_value = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
    payload = "|".join(
        normalize_text(v)
        for v in (type_value, sport or "", country or "", canonical_name)
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{slugify(type_value)}_{slugify(canonical_name)}_{digest}"


class EntityResolver:
    def __init__(
        self,
        entities: Iterable[Entity] | None = None,
        *,
        fuzzy_threshold: float = 0.92,
    ) -> None:
        if not 0 <= fuzzy_threshold <= 1:
            raise ValueError("fuzzy_threshold must be between 0 and 1")
        self.fuzzy_threshold = fuzzy_threshold
        self._entities: dict[str, Entity] = {}
        self._name_index: dict[str, set[str]] = {}
        for entity in entities or ():
            self.register(entity)

    def register(self, entity: Entity) -> None:
        if not entity.canonical_name.strip():
            raise ValueError("canonical_name must not be empty")
        if entity.entity_id in self._entities:
            if self._entities[entity.entity_id] != entity:
                raise ValueError(f"entity_id already registered: {entity.entity_id}")
            return
        self._entities[entity.entity_id] = entity
        for name in {entity.canonical_name, *entity.aliases}:
            key = normalize_text(name)
            if key:
                self._name_index.setdefault(key, set()).add(entity.entity_id)

    def add(
        self,
        canonical_name: str,
        *,
        entity_type: EntityType = EntityType.UNKNOWN,
        sport: str | None = None,
        country: str | None = None,
        league: str | None = None,
        aliases: Sequence[str] = (),
        entity_id: str | None = None,
    ) -> Entity:
        entity = Entity(
            entity_id=entity_id or stable_entity_id(
                canonical_name, entity_type, sport, country
            ),
            canonical_name=canonical_name.strip(),
            entity_type=entity_type,
            sport=sport,
            country=country,
            league=league,
            aliases=tuple(dict.fromkeys(a.strip() for a in aliases if a.strip())),
        )
        self.register(entity)
        return entity

    def resolve(
        self,
        text: str,
        *,
        entity_type: EntityType | None = None,
        sport: str | None = None,
        country: str | None = None,
        league: str | None = None,
        allow_fuzzy: bool = True,
    ) -> EntityMatch | None:
        normalized = normalize_text(text)
        if not normalized:
            return None

        exact = self._filter(
            self._name_index.get(normalized, set()),
            entity_type=entity_type,
            sport=sport,
            country=country,
            league=league,
        )
        if len(exact) == 1:
            return EntityMatch(exact[0], text, normalized, 1.0, "exact")
        if len(exact) > 1 or not allow_fuzzy:
            return None

        best = None
        best_score = 0.0
        tied = False
        for entity in self._filter(
            self._entities.keys(),
            entity_type=entity_type,
            sport=sport,
            country=country,
            league=league,
        ):
            score = max(
                self._token_similarity(normalized, normalize_text(name))
                for name in (entity.canonical_name, *entity.aliases)
            )
            if score > best_score:
                best, best_score, tied = entity, score, False
            elif score == best_score and score > 0:
                tied = True

        if best is None or tied or best_score < self.fuzzy_threshold:
            return None
        return EntityMatch(best, text, normalized, round(best_score, 4), "fuzzy")

    def extract_from_text(
        self,
        text: str,
        *,
        entity_type: EntityType | None = None,
        sport: str | None = None,
    ) -> list[EntityMatch]:
        article = f" {normalize_text(text)} "
        found: dict[str, EntityMatch] = {}
        for alias, ids in sorted(self._name_index.items(), key=lambda x: len(x[0]), reverse=True):
            if f" {alias} " not in article:
                continue
            candidates = self._filter(ids, entity_type=entity_type, sport=sport)
            if len(candidates) != 1:
                continue
            entity = candidates[0]
            found[entity.entity_id] = EntityMatch(
                entity, alias, alias, 1.0, "contained"
            )
        return list(found.values())

    def resolve_many(self, values: Iterable[str], **filters: object) -> list[EntityMatch]:
        out: list[EntityMatch] = []
        seen: set[str] = set()
        for value in values:
            match = self.resolve(value, **filters)
            if match and match.entity.entity_id not in seen:
                out.append(match)
                seen.add(match.entity.entity_id)
        return out

    def to_dict(self) -> list[dict[str, object]]:
        return [
            {
                "entity_id": e.entity_id,
                "canonical_name": e.canonical_name,
                "entity_type": e.entity_type.value,
                "sport": e.sport,
                "country": e.country,
                "league": e.league,
                "aliases": list(e.aliases),
            }
            for e in self._entities.values()
        ]

    @classmethod
    def from_dicts(cls, rows: Iterable[Mapping[str, object]]) -> "EntityResolver":
        resolver = cls()
        for row in rows:
            resolver.add(
                str(row["canonical_name"]),
                entity_type=EntityType(str(row.get("entity_type", "unknown"))),
                sport=_opt(row.get("sport")),
                country=_opt(row.get("country")),
                league=_opt(row.get("league")),
                aliases=tuple(str(v) for v in row.get("aliases", []) or []),
                entity_id=_opt(row.get("entity_id")),
            )
        return resolver

    def _filter(
        self,
        ids: Iterable[str],
        *,
        entity_type: EntityType | None = None,
        sport: str | None = None,
        country: str | None = None,
        league: str | None = None,
    ) -> list[Entity]:
        result = []
        for entity_id in ids:
            e = self._entities[entity_id]
            if entity_type is not None and e.entity_type != entity_type:
                continue
            if sport is not None and normalize_text(e.sport or "") != normalize_text(sport):
                continue
            if country is not None and normalize_text(e.country or "") != normalize_text(country):
                continue
            if league is not None and normalize_text(e.league or "") != normalize_text(league):
                continue
            result.append(e)
        return result

    @staticmethod
    def _token_similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        a, b = set(left.split()), set(right.split())
        if not a or not b:
            return 0.0
        jaccard = len(a & b) / len(a | b)
        length = min(len(left), len(right)) / max(len(left), len(right))
        bonus = 0.05 if left.startswith(right) or right.startswith(left) else 0.0
        return min(1.0, 0.75 * jaccard + 0.25 * length + bonus)


def _opt(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_default_resolver() -> EntityResolver:
    resolver = EntityResolver()
    resolver.add(
        "Manchester United",
        entity_type=EntityType.TEAM,
        sport="football",
        country="England",
        league="Premier League",
        aliases=("Man United", "Man Utd", "MUFC"),
    )
    resolver.add(
        "Manchester City",
        entity_type=EntityType.TEAM,
        sport="football",
        country="England",
        league="Premier League",
        aliases=("Man City", "MCFC"),
    )
    resolver.add(
        "Bayern Munich",
        entity_type=EntityType.TEAM,
        sport="football",
        country="Germany",
        league="Bundesliga",
        aliases=("FC Bayern", "Bayern München", "FC Bayern München"),
    )
    resolver.add(
        "Borussia Dortmund",
        entity_type=EntityType.TEAM,
        sport="football",
        country="Germany",
        league="Bundesliga",
        aliases=("BVB", "Dortmund"),
    )
    resolver.add(
        "Premier League",
        entity_type=EntityType.LEAGUE,
        sport="football",
        country="England",
        aliases=("English Premier League", "EPL"),
    )
    resolver.add(
        "Bundesliga",
        entity_type=EntityType.LEAGUE,
        sport="football",
        country="Germany",
        aliases=("German Bundesliga", "1. Bundesliga"),
    )
    return resolver

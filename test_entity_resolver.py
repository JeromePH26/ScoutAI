from scout_ai.entity_resolver import (
    EntityResolver,
    EntityType,
    build_default_resolver,
    normalize_text,
    stable_entity_id,
)


def test_normalization():
    assert normalize_text("Bayern München!") == "bayern munchen"


def test_stable_id():
    assert stable_entity_id("Manchester United", EntityType.TEAM, "football", "England") == \
           stable_entity_id("Manchester United", EntityType.TEAM, "football", "England")


def test_alias_resolution():
    match = build_default_resolver().resolve("Man Utd", entity_type=EntityType.TEAM)
    assert match is not None
    assert match.entity.canonical_name == "Manchester United"


def test_accented_alias():
    match = build_default_resolver().resolve("Bayern München", entity_type=EntityType.TEAM)
    assert match is not None
    assert match.entity.canonical_name == "Bayern Munich"


def test_wrong_type_is_rejected():
    assert build_default_resolver().resolve(
        "Premier League", entity_type=EntityType.TEAM
    ) is None


def test_ambiguous_alias_is_rejected():
    resolver = EntityResolver()
    resolver.add("Springfield United", entity_type=EntityType.TEAM, aliases=("United",))
    resolver.add("Riverside United", entity_type=EntityType.TEAM, aliases=("United",))
    assert resolver.resolve("United", entity_type=EntityType.TEAM) is None


def test_extract_from_text():
    matches = build_default_resolver().extract_from_text(
        "BVB trifft auf FC Bayern München in der Bundesliga.",
        sport="football",
    )
    names = {m.entity.canonical_name for m in matches}
    assert {"Borussia Dortmund", "Bayern Munich", "Bundesliga"} <= names

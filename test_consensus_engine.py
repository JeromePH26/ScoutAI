from dataclasses import dataclass, field
from datetime import datetime, timezone

from scout_ai.consensus_engine import (
    build_consensus_bundle,
    evaluate_cluster,
    rank_consensus,
)


NOW = datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)


@dataclass
class FakeCluster:
    cluster_id: str
    articles: list[dict]
    team_entity_ids: set[str] = field(default_factory=set)
    league_entity_ids: set[str] = field(default_factory=set)


def article(
    source,
    text,
    *,
    quality=0.9,
    category="wire",
    tier="A",
    published="2026-07-25T17:00:00+00:00",
):
    return {
        "title": text,
        "snippet": text,
        "source": source,
        "source_quality_hint": quality,
        "source_category": category,
        "source_tier": tier,
        "published_at": published,
        "link": f"https://example.com/{source}",
    }


def strong_cluster():
    return FakeCluster(
        cluster_id="event_strong",
        articles=[
            article(
                "BBC Sport",
                "Confirmed injury: Bayern player ruled out before Borussia Dortmund match.",
                quality=0.92,
            ),
            article(
                "Reuters Sports",
                "Official team news confirms Bayern player ruled out against Borussia Dortmund.",
                quality=0.94,
                category="discovery",
            ),
        ],
        team_entity_ids={"team_bayern", "team_dortmund"},
        league_entity_ids={"league_bundesliga"},
    )


def test_two_strong_independent_sources_are_analyzed():
    result = evaluate_cluster(strong_cluster(), now=NOW)

    assert result.decision == "ANALYZE"
    assert result.ready_for_ai is True
    assert result.independent_sources == 2
    assert result.confidence >= 64


def test_single_official_source_remains_watch():
    cluster = FakeCluster(
        cluster_id="event_official",
        articles=[
            article(
                "Official Club Website",
                "Official confirmed lineup and one player ruled out.",
                quality=0.98,
                category="official",
            )
        ],
        team_entity_ids={"team_home", "team_away"},
    )

    result = evaluate_cluster(cluster, now=NOW)

    assert result.decision == "WATCH"
    assert result.official_sources == 1
    assert "Nur eine unabhängige Quelle" in result.warnings


def test_conflicting_reports_are_not_analyzed():
    cluster = FakeCluster(
        cluster_id="event_conflict",
        articles=[
            article(
                "BBC Sport",
                "Confirmed: player ruled out and unavailable for the match.",
                quality=0.92,
            ),
            article(
                "Reuters Sports",
                "The player is available and fit to play.",
                quality=0.94,
            ),
        ],
        team_entity_ids={"team_home", "team_away"},
    )

    result = evaluate_cluster(cluster, now=NOW)

    assert result.decision != "ANALYZE"
    assert result.conflict_penalty >= 0.18
    assert "Widersprüchliche Meldungen erkannt" in result.warnings


def test_missing_match_identity_blocks_analyze():
    cluster = FakeCluster(
        cluster_id="event_unknown",
        articles=[
            article(
                "BBC Sport",
                "Confirmed injury update before tonight's match.",
                quality=0.92,
            ),
            article(
                "Reuters Sports",
                "Official injury update confirms a player is ruled out.",
                quality=0.94,
            ),
        ],
    )

    result = evaluate_cluster(cluster, now=NOW)

    assert result.decision != "ANALYZE"
    assert result.entity_completeness < 0.55


def test_same_source_is_not_counted_twice():
    cluster = FakeCluster(
        cluster_id="event_same_source",
        articles=[
            article("BBC Sport", "Confirmed injury before the match."),
            article("BBC Sport", "Official lineup confirms the injury."),
        ],
        team_entity_ids={"team_home", "team_away"},
    )

    result = evaluate_cluster(cluster, now=NOW)

    assert result.independent_sources == 1
    assert result.decision == "WATCH"


def test_rank_consensus_puts_analyze_first():
    weak = FakeCluster(
        cluster_id="event_weak",
        articles=[
            article(
                "Reddit",
                "Prediction and opinion about a possible lineup.",
                quality=0.38,
                category="community",
                tier="D",
            )
        ],
    )

    ranked = rank_consensus([weak, strong_cluster()], now=NOW)

    assert ranked[0][1].decision == "ANALYZE"
    assert ranked[0][1].cluster_id == "event_strong"


def test_bundle_contains_audit_metadata_and_policy():
    cluster = strong_cluster()
    decision = evaluate_cluster(cluster, now=NOW)
    bundle = build_consensus_bundle(cluster, decision)

    assert "CONSENSUS_DECISION=ANALYZE" in bundle
    assert "INDEPENDENT_SOURCES=2" in bundle
    assert "TEAM_ENTITY_IDS=team_bayern,team_dortmund" in bundle
    assert "never authorizes a bet" in bundle

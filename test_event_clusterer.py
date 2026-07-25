from scout_ai.entity_resolver import build_default_resolver
from scout_ai.event_clusterer import (
    article_similarity,
    build_event_bundle,
    cluster_events,
    enrich_article_with_entities,
)


def article(title, snippet, source, published_at):
    return {
        "title": title,
        "snippet": snippet,
        "source": source,
        "link": f"https://example.com/{source}/{title}",
        "published_at": published_at,
    }


def test_enrichment_detects_teams_and_league():
    enriched = enrich_article_with_entities(
        article(
            "BVB trifft Bayern München",
            "Borussia Dortmund spielt gegen FC Bayern in der Bundesliga.",
            "BBC",
            "2026-07-25T12:00:00+00:00",
        ),
        build_default_resolver(),
    )

    assert {"Borussia Dortmund", "Bayern Munich"} <= set(enriched["teams"])
    assert "Bundesliga" in enriched["leagues"]


def test_same_match_clusters_across_sources():
    articles = [
        article(
            "BVB gegen Bayern: Spieler fällt aus",
            "Borussia Dortmund trifft FC Bayern München in der Bundesliga.",
            "BBC",
            "2026-07-25T12:00:00+00:00",
        ),
        article(
            "Bayern Munich team news before Dortmund",
            "FC Bayern plays Borussia Dortmund. An injury was confirmed.",
            "ESPN",
            "2026-07-25T13:00:00+00:00",
        ),
    ]

    clusters = cluster_events(articles)

    assert len(clusters) == 1
    assert clusters[0].article_count == 2
    assert clusters[0].independent_sources == 2


def test_different_matches_do_not_merge():
    articles = [
        article(
            "BVB gegen Bayern",
            "Borussia Dortmund trifft FC Bayern München.",
            "BBC",
            "2026-07-25T12:00:00+00:00",
        ),
        article(
            "Manchester derby",
            "Manchester United trifft Manchester City.",
            "ESPN",
            "2026-07-25T13:00:00+00:00",
        ),
    ]

    clusters = cluster_events(articles)

    assert len(clusters) == 2


def test_articles_outside_time_window_do_not_merge():
    resolver = build_default_resolver()
    left = enrich_article_with_entities(
        article(
            "BVB gegen Bayern",
            "Borussia Dortmund trifft FC Bayern München.",
            "BBC",
            "2026-07-20T12:00:00+00:00",
        ),
        resolver,
    )
    right = enrich_article_with_entities(
        article(
            "Bayern gegen Dortmund",
            "FC Bayern München trifft Borussia Dortmund.",
            "ESPN",
            "2026-07-25T12:00:00+00:00",
        ),
        resolver,
    )

    assert article_similarity(left, right, max_time_gap_hours=72) == 0.0


def test_event_bundle_contains_cluster_metadata():
    clusters = cluster_events(
        [
            article(
                "BVB gegen Bayern",
                "Borussia Dortmund trifft FC Bayern München.",
                "BBC",
                "2026-07-25T12:00:00+00:00",
            )
        ]
    )

    bundle = build_event_bundle(clusters[0])

    assert "EVENT_CLUSTER_ID=" in bundle
    assert "ARTICLE_COUNT=1" in bundle
    assert "SOURCE_1=BBC" in bundle

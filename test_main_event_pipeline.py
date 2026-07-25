from datetime import datetime, timezone

import scout_ai.main as main


def _articles():
    return [
        {
            'title': 'BVB gegen Bayern: confirmed injury',
            'snippet': 'Borussia Dortmund trifft Bayern in der Bundesliga. Player ruled out.',
            'source': 'BBC Sport',
            'source_tier': 'A',
            'source_category': 'wire',
            'source_quality_hint': 0.92,
            'published_at': datetime.now(timezone.utc).isoformat(),
            'link': 'https://bbc.example/1',
        },
        {
            'title': 'Bayern team news before Dortmund',
            'snippet': 'Bayern plays Borussia Dortmund. Injury confirmed by the club.',
            'source': 'ESPN',
            'source_tier': 'A',
            'source_category': 'wire',
            'source_quality_hint': 0.88,
            'published_at': datetime.now(timezone.utc).isoformat(),
            'link': 'https://espn.example/2',
        },
    ]


def test_pipeline_downgrades_action_without_market_odds(monkeypatch):
    sent=[]
    saved=[]
    main._analyzed_clusters.clear()
    monkeypatch.setattr(main, 'analyze_snippet', lambda *_a, **_k: [{
        'status':'ACTION', 'match':'Bayern Munich vs Borussia Dortmund',
        'market': {'bet':'Bayern DNB', 'market_odds':None}
    }])
    monkeypatch.setattr(main, 'send_telegram_alert', lambda signal: sent.append(signal))
    monkeypatch.setattr(main, 'process_consensus', lambda match, bet, source, signal: (saved.append(signal.copy()) or (1, True)))

    stats=main.process_articles(_articles())

    assert stats['ai_calls'] == 1
    assert stats['signals'] == 1
    assert sent[0]['status'] == 'WATCH'
    assert sent[0]['consensus_reached'].startswith('WATCH | EVENT ')
    assert saved[0]['consensus_reached'] == sent[0]['consensus_reached']
    assert sent[0]['event_cluster_id']


def test_cluster_cooldown_prevents_repeat_ai_call(monkeypatch):
    main._analyzed_clusters.clear()
    calls=[]
    monkeypatch.setattr(main, 'analyze_snippet', lambda *_a, **_k: (calls.append(1) or []))

    first=main.process_articles(_articles())
    second=main.process_articles(_articles())

    assert first['ai_calls'] == 1
    assert second['ai_calls'] == 0
    assert len(calls) == 1

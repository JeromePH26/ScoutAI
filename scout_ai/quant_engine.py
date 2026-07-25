import math
import os
import re
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable


SOURCE_WEIGHTS = {
    "official": 0.98,
    "reuters": 0.94,
    "bbc": 0.92,
    "espn": 0.88,
    "sky": 0.86,
    "the athletic": 0.86,
    "hl tv": 0.78,
    "hltv": 0.78,
    "betfair": 0.72,
    "reddit": 0.42,
    "twitter": 0.38,
    "x.com": 0.38,
}

POSITIVE_TERMS = {
    "confirmed": 1.00,
    "official": 1.00,
    "ruled out": 0.95,
    "starting lineup": 0.95,
    "confirmed lineup": 0.95,
    "suspended": 0.90,
    "injury": 0.78,
    "doubtful": 0.72,
    "questionable": 0.62,
    "late change": 0.86,
    "sharp money": 0.82,
    "line movement": 0.85,
    "odds shortened": 0.88,
    "odds drift": 0.82,
    "unusual volume": 0.82,
    "weather warning": 0.68,
    "heavy rain": 0.62,
    "strong wind": 0.62,
}

NOISE_TERMS = {
    "season preview": 0.25,
    "weekly roundup": 0.25,
    "opinion": 0.15,
    "rumour": 0.20,
    "rumor": 0.20,
    "best bets": 0.08,
    "prediction": 0.06,
    "tips today": 0.08,
}

STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "today", "tomorrow",
    "best", "bet", "bets", "pick", "picks", "prediction", "analysis", "preview",
    "news", "latest", "football", "soccer", "nba", "nfl", "ufc", "vs", "v",
    "der", "die", "das", "und", "für", "mit", "von", "heute", "morgen",
}


@dataclass
class ClusterScore:
    fingerprint: str
    article_count: int
    independent_sources: int
    source_quality: float
    signal_strength: float
    freshness: float
    corroboration: float
    diversity: float
    conflict_penalty: float
    raw_score: float
    confidence: int
    decision: str

    def as_dict(self):
        return asdict(self)


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9äöüß\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(article: dict) -> set[str]:
    text = _norm(f"{article.get('title', '')} {article.get('snippet', '')}")
    tokens = {
        t for t in re.findall(r"[a-z0-9äöüß-]{3,}", text)
        if t not in STOPWORDS and not t.isdigit()
    }
    # Seltene/konkrete Tokens priorisieren, Paketgröße begrenzen.
    return set(sorted(tokens, key=lambda x: (-len(x), x))[:35])


def _source_name(article: dict) -> str:
    source = article.get("source") or article.get("link") or ""
    return _norm(source)


def source_quality(article: dict) -> float:
    source = _source_name(article)
    for marker, weight in SOURCE_WEIGHTS.items():
        if marker in source:
            return weight
    # RSS ohne bekannte Quelle: neutral-konservativ.
    return 0.58


def signal_strength(article: dict) -> float:
    text = _norm(f"{article.get('title', '')} {article.get('snippet', '')}")
    positive = sum(weight for term, weight in POSITIVE_TERMS.items() if term in text)
    noise = sum(weight for term, weight in NOISE_TERMS.items() if term in text)
    # Sättigende Transformation: mehrere Signale helfen, aber nicht linear unbegrenzt.
    strength = 1.0 - math.exp(-positive / 1.7)
    return max(0.0, min(1.0, strength - noise))


def freshness(article: dict) -> float:
    value = article.get("published_at")
    if not value:
        return 0.62
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
        # Halbwertszeit ca. 18 Stunden.
        return max(0.10, math.exp(-math.log(2) * age_h / 18.0))
    except Exception:
        return 0.55


def similarity(a: dict, b: dict) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    title_a = _norm(a.get("title", ""))
    title_b = _norm(b.get("title", ""))
    title_bonus = 0.10 if any(tok in title_b for tok in _tokens({"title": title_a})) else 0.0
    return min(1.0, jaccard + title_bonus)


def cluster_articles(articles: list[dict], threshold: float | None = None) -> list[list[dict]]:
    threshold = threshold or float(os.getenv("CLUSTER_SIMILARITY", "0.16"))
    clusters: list[list[dict]] = []

    ranked = sorted(
        articles,
        key=lambda a: source_quality(a) * 0.45 + signal_strength(a) * 0.40 + freshness(a) * 0.15,
        reverse=True,
    )

    for article in ranked:
        best_idx = None
        best_similarity = 0.0
        for idx, cluster in enumerate(clusters):
            sim = max(similarity(article, member) for member in cluster[:6])
            if sim > best_similarity:
                best_similarity = sim
                best_idx = idx
        if best_idx is not None and best_similarity >= threshold:
            clusters[best_idx].append(article)
        else:
            clusters.append([article])

    return clusters


def _contradiction_penalty(cluster: list[dict]) -> float:
    text = " ".join(_norm(a.get("snippet", "")) for a in cluster)
    pairs = [
        ("ruled out", "fit to play"),
        ("out", "available"),
        ("confirmed", "unconfirmed"),
        ("suspended", "cleared"),
        ("postponed", "goes ahead"),
    ]
    hits = sum(1 for left, right in pairs if left in text and right in text)
    return min(0.45, hits * 0.16)


def score_cluster(cluster: list[dict]) -> ClusterScore:
    qualities = [source_quality(a) for a in cluster]
    strengths = [signal_strength(a) for a in cluster]
    fresh = [freshness(a) for a in cluster]
    sources = {_source_name(a) or a.get("link", "") for a in cluster}
    independent = max(1, len(sources))

    source_q = sum(qualities) / len(qualities)
    signal = sum(strengths) / len(strengths)
    fresh_q = sum(fresh) / len(fresh)

    # Diminishing returns: 2. und 3. unabhängige Quelle sind besonders wertvoll.
    corroboration = 1.0 - math.exp(-0.72 * max(0, independent - 1))
    diversity = min(1.0, independent / max(2, len(cluster)))
    penalty = _contradiction_penalty(cluster)

    # Gewichtete lokale Evidenzfunktion.
    raw = (
        0.30 * source_q
        + 0.29 * signal
        + 0.16 * fresh_q
        + 0.19 * corroboration
        + 0.06 * diversity
        - penalty
    )
    raw = max(0.0, min(1.0, raw))

    # Logistische Kalibrierung um den Entscheidungsbereich.
    confidence = round(100 / (1 + math.exp(-9.0 * (raw - 0.55))))

    analyze_threshold = int(os.getenv("ANALYZE_CONFIDENCE_MIN", "58"))
    watch_threshold = int(os.getenv("WATCH_CONFIDENCE_MIN", "38"))

    if confidence >= analyze_threshold and (
        independent >= 2 or max(qualities) >= 0.90 or max(strengths) >= 0.88
    ):
        decision = "ANALYZE"
    elif confidence >= watch_threshold:
        decision = "WATCH"
    else:
        decision = "SKIP"

    identity = "|".join(sorted(_norm(a.get("title", "")) for a in cluster))
    fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]

    return ClusterScore(
        fingerprint=fingerprint,
        article_count=len(cluster),
        independent_sources=independent,
        source_quality=round(source_q, 4),
        signal_strength=round(signal, 4),
        freshness=round(fresh_q, 4),
        corroboration=round(corroboration, 4),
        diversity=round(diversity, 4),
        conflict_penalty=round(penalty, 4),
        raw_score=round(raw, 4),
        confidence=confidence,
        decision=decision,
    )


def rank_clusters(clusters: Iterable[list[dict]]) -> list[tuple[list[dict], ClusterScore]]:
    scored = [(cluster, score_cluster(cluster)) for cluster in clusters if cluster]
    return sorted(scored, key=lambda item: item[1].confidence, reverse=True)


def build_compact_bundle(cluster: list[dict], score: ClusterScore, max_articles: int = 6) -> str:
    lines = [
        f"LOCAL_QUANT_SCORE={score.confidence}",
        f"INDEPENDENT_SOURCES={score.independent_sources}",
        f"SOURCE_QUALITY={score.source_quality}",
        f"SIGNAL_STRENGTH={score.signal_strength}",
        f"FRESHNESS={score.freshness}",
        f"CONFLICT_PENALTY={score.conflict_penalty}",
    ]
    for idx, article in enumerate(cluster[:max_articles], start=1):
        snippet = re.sub(r"\s+", " ", article.get("snippet", ""))[:900]
        lines.append(
            f"\nSOURCE_{idx}\n"
            f"TITLE={article.get('title', '')}\n"
            f"URL={article.get('link', '')}\n"
            f"TEXT={snippet}"
        )
    return "\n".join(lines)

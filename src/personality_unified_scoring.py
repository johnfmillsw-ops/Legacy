"""
Deterministic personality score integration.

No external AI requests.
Original assessment scores remain unchanged.
"""

from math import isfinite, fsum

SCORING_VERSION = 1

BASELINE_WEIGHT = 20.0

CORE_TRAITS = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "emotional_stability",
)


def validate_score(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a valid score.")

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid numeric score.")

    if not isfinite(value) or not 0 <= value <= 100:
        raise ValueError("Score must be between 0 and 100.")

    return value


def combine_trait(baseline=None, evidence=()):
    if baseline is not None:
        baseline = validate_score(baseline)

    independent = {}

    for item in evidence:
        key = item.get("independence_key")

        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                "Evidence requires an independence key."
            )

        score = validate_score(item["score"])
        confidence = validate_score(item["confidence"])

        relevance = validate_score(
            item.get("relevance", 100)
        )

        weight = (
            confidence / 100
            * relevance / 100
        )

        if weight <= 0:
            continue

        independent.setdefault(key, []).append(
            (score, weight)
        )

    weighted_scores = []
    weights = []

    for records in independent.values():
        # Repeated evidence receives no additional
        # aggregate weight within the same group.
        group_weight = max(
            weight for _, weight in records
        )

        group_score = fsum(
            score * weight
            for score, weight in records
        ) / fsum(
            weight for _, weight in records
        )

        weighted_scores.append(
            group_score * group_weight
        )

        weights.append(group_weight)

    memory_weight = fsum(weights)

    baseline_weight = (
        BASELINE_WEIGHT
        if baseline is not None
        else 0.0
    )

    total_weight = baseline_weight + memory_weight

    if total_weight == 0:
        score = None

    else:
        numerator = fsum(weighted_scores)

        if baseline is not None:
            numerator += baseline * baseline_weight

        score = round(
            numerator / total_weight,
            2,
        )

    if baseline is not None and memory_weight > 0:
        method = "integrated"

    elif baseline is not None:
        method = "questionnaire"

    elif memory_weight > 0:
        method = "memory_evidence"

    else:
        method = "insufficient_evidence"

    return {
        "score": score,
        "method": method,
        "scoring_version": SCORING_VERSION,
        "baseline_weight": baseline_weight,
        "memory_weight": round(memory_weight, 4),
        "independent_evidence_count": len(independent),
        "baseline_influence": (
            round(
                100 * baseline_weight / total_weight,
                2,
            )
            if total_weight else None
        ),
    }


def build_unified_scores(
    baseline_scores=None,
    evidence_by_trait=None,
):
    baseline_scores = baseline_scores or {}
    evidence_by_trait = evidence_by_trait or {}

    return {
        trait: combine_trait(
            baseline=baseline_scores.get(trait),
            evidence=evidence_by_trait.get(trait, ()),
        )
        for trait in CORE_TRAITS
    }


def run_tests():

    def record(key, score, confidence=100, relevance=100):
        return {
            "independence_key": key,
            "score": score,
            "confidence": confidence,
            "relevance": relevance,
        }

    assert combine_trait()["score"] is None
    print("Missing evidence handling: PASSED")

    assert combine_trait(75)["score"] == 75
    assert combine_trait(0)["score"] == 0
    assert combine_trait(100)["score"] == 100
    print("Baseline-only scoring: PASSED")

    assert combine_trait(
        evidence=[record("event-a", 80)]
    )["score"] == 80
    print("Memory-only scoring: PASSED")

    evidence = [
        record(str(i), 90)
        for i in range(20)
    ]

    result = combine_trait(50, evidence)

    assert result["score"] == 70
    assert result["baseline_influence"] == 50
    print("Weighted integration: PASSED")

    duplicates = [
        record("same-event", 90)
        for _ in range(100)
    ]

    single = combine_trait(
        50, [record("same-event", 90)]
    )

    repeated = combine_trait(50, duplicates)

    assert single == repeated
    print("Repeated evidence weight protection: PASSED")

    assert combine_trait(
        50, [record("event-a", 90, 0)]
    )["score"] == 50
    print("Zero-confidence evidence exclusion: PASSED")

    high = combine_trait(
        50, [record("event-a", 90, 100)]
    )["score"]

    low = combine_trait(
        50, [record("event-a", 90, 10)]
    )["score"]

    assert high > low > 50
    print("Confidence weighting: PASSED")

    relevant = combine_trait(
        50, [record("event-a", 90, 100, 100)]
    )["score"]

    less_relevant = combine_trait(
        50, [record("event-a", 90, 100, 10)]
    )["score"]

    assert relevant > less_relevant
    print("Relevance weighting: PASSED")

    assert combine_trait(
        50, evidence[:-10]
    )["score"] < result["score"]

    assert combine_trait(50, [])["score"] == 50
    print("Evidence removal recalculation: PASSED")

    scores = build_unified_scores(
        baseline_scores={
            "openness": 85,
            "extraversion": 40,
        }
    )

    assert len(scores) == 5
    assert scores["openness"]["score"] == 85
    assert scores["extraversion"]["score"] == 40
    assert scores["agreeableness"]["score"] is None
    print("Five-trait framework integration: PASSED")

    for invalid in (
        -1, 101, float("nan"),
        float("inf"), True, "invalid",
    ):
        try:
            combine_trait(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Invalid score accepted."
            )

    print("Invalid score protection: PASSED")

    print("\nAll unified scoring tests passed.")
    print("No database changes.")
    print("No external AI requests.")


if __name__ == "__main__":
    print("LEGACY UNIFIED PERSONALITY SCORING")
    print("=" * 50)
    run_tests()

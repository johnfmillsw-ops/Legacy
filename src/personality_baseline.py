"""Versioned IPIP personality baseline assessment."""

from collections import Counter

INSTRUMENT_ID = "ipip_big_five_50"
INSTRUMENT_VERSION = 1

SOURCE_URL = (
    "https://ipip.ori.org/New_IPIP-50-item-scale.htm"
)

TRAITS = (
    "extraversion",
    "agreeableness",
    "conscientiousness",
    "emotional_stability",
    "openness",
)

RESPONSE_OPTIONS = {
    1: "Very inaccurate",
    2: "Moderately inaccurate",
    3: "Neither accurate nor inaccurate",
    4: "Moderately accurate",
    5: "Very accurate",
}

# Original public-domain IPIP items.
# Each tuple contains wording and scoring direction.

ITEMS = (
    ("Am the life of the party.", 1),
    ("Feel little concern for others.", -1),
    ("Am always prepared.", 1),
    ("Get stressed out easily.", -1),
    ("Have a rich vocabulary.", 1),
    ("Don't talk a lot.", -1),
    ("Am interested in people.", 1),
    ("Leave my belongings around.", -1),
    ("Am relaxed most of the time.", 1),
    ("Have difficulty understanding abstract ideas.", -1),
    ("Feel comfortable around people.", 1),
    ("Insult people.", -1),
    ("Pay attention to details.", 1),
    ("Worry about things.", -1),
    ("Have a vivid imagination.", 1),
    ("Keep in the background.", -1),
    ("Sympathize with others' feelings.", 1),
    ("Make a mess of things.", -1),
    ("Seldom feel blue.", 1),
    ("Am not interested in abstract ideas.", -1),
    ("Start conversations.", 1),
    ("Am not interested in other people's problems.", -1),
    ("Get chores done right away.", 1),
    ("Am easily disturbed.", -1),
    ("Have excellent ideas.", 1),
    ("Have little to say.", -1),
    ("Have a soft heart.", 1),
    ("Often forget to put things back in their proper place.", -1),
    ("Get upset easily.", -1),
    ("Do not have a good imagination.", -1),
    ("Talk to a lot of different people at parties.", 1),
    ("Am not really interested in others.", -1),
    ("Like order.", 1),
    ("Change my mood a lot.", -1),
    ("Am quick to understand things.", 1),
    ("Don't like to draw attention to myself.", -1),
    ("Take time out for others.", 1),
    ("Shirk my duties.", -1),
    ("Have frequent mood swings.", -1),
    ("Use difficult words.", 1),
    ("Don't mind being the center of attention.", 1),
    ("Feel others' emotions.", 1),
    ("Follow a schedule.", 1),
    ("Get irritated easily.", -1),
    ("Spend time reflecting on things.", 1),
    ("Am quiet around strangers.", -1),
    ("Make people feel at ease.", 1),
    ("Am exacting in my work.", 1),
    ("Often feel blue.", -1),
    ("Am full of ideas.", 1),
)

QUESTIONS = tuple(
    {
        "id": str(index + 1),
        "text": wording,
        "trait": TRAITS[index % 5],
        "direction": direction,
    }
    for index, (wording, direction)
    in enumerate(ITEMS)
)


def get_assessment():
    """Return questionnaire without scoring keys."""

    return {
        "instrument": INSTRUMENT_ID,
        "version": INSTRUMENT_VERSION,
        "source": SOURCE_URL,
        "title": "Personality Baseline Assessment",
        "instructions": (
            "Describe yourself as you generally are now, "
            "rather than how you wish to be. "
            "Indicate how accurately each statement "
            "describes you, compared with people "
            "of a similar age and sex."
        ),
        "response_options": RESPONSE_OPTIONS.copy(),
        "questions": [
            {
                "id": question["id"],
                "text": question["text"],
            }
            for question in QUESTIONS
        ],
    }


def validate_responses(responses, complete=True):
    """Validate complete assessments or partial drafts."""

    if not isinstance(responses, dict):
        raise ValueError("Responses must be an object.")

    expected = {question["id"] for question in QUESTIONS}
    actual = set(responses)

    if actual - expected:
        raise ValueError("Unknown question identifiers.")

    if complete and actual != expected:
        raise ValueError("All 50 questions must be answered.")

    for question_id, value in responses.items():

        if type(value) is not int or not 1 <= value <= 5:
            raise ValueError(
                f"Invalid response for question {question_id}."
            )

    return responses.copy()


def score_assessment(responses):
    """Calculate raw and normalized scores without AI."""

    responses = validate_responses(responses)

    raw_scores = {trait: 0 for trait in TRAITS}
    counts = Counter()

    for question in QUESTIONS:

        value = responses[question["id"]]

        if question["direction"] == -1:
            value = 6 - value

        trait = question["trait"]

        raw_scores[trait] += value
        counts[trait] += 1

    normalized = {
        trait: round(
            100 * (
                raw_scores[trait] - counts[trait]
            ) / (4 * counts[trait]),
            2,
        )
        for trait in TRAITS
    }

    return {
        "instrument": INSTRUMENT_ID,
        "version": INSTRUMENT_VERSION,
        "raw_scores": raw_scores,
        "scores": normalized,
        "item_count": dict(counts),
        "score_type": "normalized_scale",
        "original_factor_names": {
            "openness": "Intellect/Imagination",
        },
    }


def run_tests():

    from personality_framework import TRAITS as LEGACY_TRAITS

    assert len(QUESTIONS) == 50

    assert len({q["id"] for q in QUESTIONS}) == 50

    assert all(trait in LEGACY_TRAITS for trait in TRAITS)

    assert Counter(
        q["trait"] for q in QUESTIONS
    ) == {trait: 10 for trait in TRAITS}

    neutral = {q["id"]: 3 for q in QUESTIONS}

    highest = {
        q["id"]: 5 if q["direction"] == 1 else 1
        for q in QUESTIONS
    }

    lowest = {
        q["id"]: 1 if q["direction"] == 1 else 5
        for q in QUESTIONS
    }

    assert all(
        value == 50
        for value in score_assessment(neutral)["scores"].values()
    )

    assert all(
        value == 100
        for value in score_assessment(highest)["scores"].values()
    )

    assert all(
        value == 0
        for value in score_assessment(lowest)["scores"].values()
    )

    # Known result: answering 5 to every item.
    assert score_assessment({
        q["id"]: 5 for q in QUESTIONS
    })["scores"] == {
        "extraversion": 50,
        "agreeableness": 60,
        "conscientiousness": 60,
        "emotional_stability": 20,
        "openness": 70,
    }

    invalid_cases = [
        {},
        {**neutral, "1": True},
        {**neutral, "1": 0},
        {**neutral, "1": 6},
        {**neutral, "1": "3"},
        {**neutral, "51": 3},
    ]

    for invalid in invalid_cases:
        try:
            score_assessment(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid responses accepted.")

    assert validate_responses(
        {"1": 4}, complete=False
    ) == {"1": 4}

    assert all(
        "direction" not in question
        and "trait" not in question
        for question in get_assessment()["questions"]
    )

    print("LEGACY PERSONALITY BASELINE")
    print("=" * 45)
    print("Instrument:", INSTRUMENT_ID)
    print("Version:", INSTRUMENT_VERSION)
    print("Questions:", len(QUESTIONS))
    print("Personality dimensions:", len(TRAITS))
    print("Framework compatibility: PASSED")
    print("Reverse scoring: PASSED")
    print("Score normalization: PASSED")
    print("Response validation: PASSED")
    print("Partial draft validation: PASSED")
    print("Scoring key protection: PASSED")
    print("All baseline tests passed.")
    print("No database changes.")
    print("No external AI requests.")


if __name__ == "__main__":
    run_tests()

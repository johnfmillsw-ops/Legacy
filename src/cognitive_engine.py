"""
Legacy Phase VII: Procedural cognitive question engine.

Deterministic generation, structural validation and scoring.
No external AI dependencies.
"""

import hashlib
import json
import random
import secrets

from copy import deepcopy

from cognitive_framework import (
    FRAMEWORK_VERSION,
    QUESTION_FORMAT,
    COGNITIVE_DOMAINS,
    validate_domain,
    validate_difficulty,
)

ENGINE_VERSION = 1

FAMILY_DOMAINS = {
    family: domain
    for domain, definition in COGNITIVE_DOMAINS.items()
    for family in definition["families"]
}


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def fingerprint(value):
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def create_seed():
    return secrets.token_hex(16)


def validate_seed(seed):
    if not isinstance(seed, str):
        raise ValueError("Seed must be a string.")

    if not 1 <= len(seed) <= 128:
        raise ValueError("Invalid seed length.")

    return seed


def question_rng(family, difficulty, seed, family_version=1):
    if not isinstance(family, str) or family not in FAMILY_DOMAINS:
        raise ValueError("Unknown question family.")

    validate_difficulty(difficulty)
    validate_seed(seed)

    if type(family_version) is not int or family_version < 1:
        raise ValueError("Invalid family version.")

    material = {
        "engine_version": ENGINE_VERSION,
        "family_version": family_version,
        "family": family,
        "difficulty": difficulty,
        "seed": seed,
    }

    return random.Random(int(fingerprint(material), 16))


def normalize_option(value):
    if not isinstance(value, str):
        raise ValueError("Answer options must be strings.")

    value = value.strip()

    if not value or len(value) > 2000:
        raise ValueError("Invalid answer option.")

    return value


def build_question(
    *,
    family,
    difficulty,
    seed,
    prompt,
    correct_answer,
    distractors,
    explanation,
    stimulus=None,
    family_version=1,
):
    rng = question_rng(
        family,
        difficulty,
        seed,
        family_version,
    )

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Question prompt is required.")

    if not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("Answer explanation is required.")

    if not isinstance(distractors, (list, tuple)):
        raise ValueError("Distractors must be a sequence.")

    correct_answer = normalize_option(correct_answer)

    answers = [correct_answer] + [
        normalize_option(value)
        for value in distractors
    ]

    if not (
        QUESTION_FORMAT["minimum_options"]
        <= len(answers)
        <= QUESTION_FORMAT["maximum_options"]
    ):
        raise ValueError("Invalid number of answer options.")

    normalized = [
        " ".join(answer.casefold().split())
        for answer in answers
    ]

    if len(normalized) != len(set(normalized)):
        raise ValueError("Duplicate answer options.")

    content = {
        "family": family,
        "family_version": family_version,
        "prompt": prompt.strip(),
        "stimulus": deepcopy(stimulus),
        "answers": sorted(answers),
        "correct_answer": correct_answer,
    }

    content_hash = fingerprint(content)

    prompt_hash = fingerprint({
        "prompt": prompt.strip(),
        "stimulus": stimulus,
    })

    rng.shuffle(answers)

    options = [
        {
            "id": chr(65 + index),
            "value": answer,
        }
        for index, answer in enumerate(answers)
    ]

    correct_option_id = next(
        option["id"]
        for option in options
        if option["value"] == correct_answer
    )

    question_id = fingerprint({
        "content_hash": content_hash,
        "engine_version": ENGINE_VERSION,
        "seed": seed,
        "difficulty": difficulty,
    })

    return {
        "id": question_id,
        "content_hash": content_hash,
        "prompt_hash": prompt_hash,
        "framework_version": FRAMEWORK_VERSION,
        "engine_version": ENGINE_VERSION,
        "family_version": family_version,
        "domain": FAMILY_DOMAINS[family],
        "family": family,
        "difficulty": difficulty,
        "seed": seed,
        "prompt": prompt.strip(),
        "stimulus": deepcopy(stimulus),
        "options": options,
        "correct_option_id": correct_option_id,
        "explanation": explanation.strip(),
        "calibration_status": "uncalibrated",
    }


def public_question(question):
    """
    Explicit allowlist for user-facing question data.

    Never expose seeds, correct answers or explanations
    before the appropriate feedback stage.
    """
    fields = (
        "id",
        "domain",
        "family",
        "difficulty",
        "prompt",
        "stimulus",
        "options",
    )

    return deepcopy({
        field: question[field]
        for field in fields
    })


def score_response(question, selected_option_id):
    if not isinstance(selected_option_id, str):
        raise ValueError("Invalid selected option.")

    valid_options = {
        option["id"]
        for option in question["options"]
    }

    if selected_option_id not in valid_options:
        raise ValueError("Unknown selected option.")

    if question["correct_option_id"] not in valid_options:
        raise ValueError("Invalid stored answer key.")

    correct = (
        selected_option_id == question["correct_option_id"]
    )

    return {
        "question_id": question["id"],
        "selected_option_id": selected_option_id,
        "correct": correct,
        "raw_points": int(correct),
    }


def run_self_tests():
    def sample(seed="test-seed", **changes):
        parameters = {
            "family": "number_sequences",
            "difficulty": 1,
            "seed": seed,
            "prompt": "2, 4, 6, 8, ?",
            "correct_answer": "10",
            "distractors": ["9", "11", "12"],
            "explanation": "Add two to each term.",
        }

        parameters.update(changes)
        return build_question(**parameters)

    question = sample()

    assert len(question["options"]) == 4
    assert question["domain"] == "quantitative_reasoning"
    print("Question construction: PASSED")

    assert question == sample()
    print("Deterministic reproduction: PASSED")

    assert question["id"] != sample("other-seed")["id"]
    print("Unique question identifiers: PASSED")

    assert (
        question["content_hash"]
        == sample("other-seed")["content_hash"]
    )
    print("Exact duplicate detection: PASSED")

    assert (
        question["content_hash"]
        == sample(distractors=["12", "9", "11"])["content_hash"]
    )
    print("Option-order-independent fingerprint: PASSED")

    positions = {
        sample(str(index))["correct_option_id"]
        for index in range(100)
    }

    assert positions == {"A", "B", "C", "D"}
    print("Randomized answer placement: PASSED")

    correct_id = question["correct_option_id"]

    assert score_response(
        question, correct_id
    )["raw_points"] == 1

    for option in question["options"]:
        if option["id"] != correct_id:
            assert score_response(
                question, option["id"]
            )["raw_points"] == 0

    print("Deterministic answer scoring: PASSED")

    public = public_question(question)

    for private_field in (
        "correct_option_id",
        "explanation",
        "seed",
        "content_hash",
        "prompt_hash",
    ):
        assert private_field not in public

    print("Private answer-key isolation: PASSED")

    public["options"].clear()
    assert len(question["options"]) == 4
    print("Public data isolation: PASSED")

    invalid_cases = (
        {"family": "unknown"},
        {"difficulty": 0},
        {"difficulty": True},
        {"seed": ""},
        {"family_version": 0},
        {"prompt": ""},
        {"explanation": ""},
        {"distractors": ["10", "11", "12"]},
        {"distractors": ["9", "9", "12"]},
        {"distractors": ["9", " 9 ", "12"]},
        {"distractors": ["9", "11"]},
        {"distractors": ["1", "2", "3", "4", "5", "6"]},
    )

    for changes in invalid_cases:
        try:
            sample(**changes)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Invalid question accepted: " + str(changes)
            )

    print("Invalid question rejection: PASSED")

    for invalid_answer in ("Z", "", None, True, []):
        try:
            score_response(question, invalid_answer)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid response accepted.")

    print("Invalid response rejection: PASSED")

    seeds = {create_seed() for _ in range(1000)}
    assert len(seeds) == 1000
    print("Random seed generation: PASSED")

    assert question["calibration_status"] == "uncalibrated"
    assert "iq" not in score_response(question, correct_id)
    print("Uncalibrated scoring safeguard: PASSED")

    print()
    print("ALL 13 COGNITIVE ENGINE TESTS PASSED")


if __name__ == "__main__":
    run_self_tests()

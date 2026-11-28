
"""
Legacy Phase VII: Working memory generators.

Experimental recognition and manipulation tasks.
Presentation and response payload separation.
"""

import json
from copy import deepcopy

from cognitive_engine import (
    build_question,
    question_rng,
    create_seed,
)

FAMILY_VERSION = 1

PRESENTATION_MS = {
    1: 4000,
    2: 5000,
    3: 6000,
    4: 7000,
    5: 8000,
}


def encode_sequence(sequence):
    return " ".join(str(value) for value in sequence)


def sequence_distractors(answer, rng):
    candidates = set()

    for left in range(len(answer)):
        for right in range(left + 1, len(answer)):
            altered = list(answer)

            altered[left], altered[right] = (
                altered[right],
                altered[left],
            )

            candidates.add(
                encode_sequence(altered)
            )

    candidates.discard(
        encode_sequence(answer)
    )

    if len(candidates) < 4:
        raise ValueError(
            "Insufficient distinct distractors."
        )

    return rng.sample(sorted(candidates), 4)


def sequence_recognition(difficulty, seed=None):
    family = "sequence_recognition"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    sequence = rng.sample(
        list(range(10)),
        difficulty + 3,
    )

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "Which sequence matches the "
            "original sequence exactly?"
        ),
        correct_answer=encode_sequence(sequence),
        distractors=sequence_distractors(
            sequence, rng
        ),
        explanation=(
            "The original sequence was "
            + encode_sequence(sequence)
            + "."
        ),
        stimulus={
            "type": "memory_sequence",
            "memorize": sequence,
            "presentation_ms": PRESENTATION_MS[difficulty],
            "instruction": (
                "Memorize the digits in their "
                "original order."
            ),
        },
        family_version=FAMILY_VERSION,
    )


def encode_locations(locations):
    return json.dumps(
        sorted(locations),
        separators=(",", ":"),
    )


def spatial_memory(difficulty, seed=None):
    family = "spatial_memory"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    grid_size = 4 if difficulty <= 3 else 5

    population = list(
        range(grid_size * grid_size)
    )

    locations = sorted(
        rng.sample(
            population,
            difficulty + 2,
        )
    )

    occupied = set(locations)

    candidates = set()

    for removed in locations:
        for added in population:
            if added in occupied:
                continue

            altered = (
                occupied - {removed}
            ) | {added}

            candidates.add(
                encode_locations(altered)
            )

    answer = encode_locations(locations)

    candidates.discard(answer)

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "Which grid matches the original "
            "highlighted locations?"
        ),
        correct_answer=answer,
        distractors=rng.sample(
            sorted(candidates), 4
        ),
        explanation=(
            "The correct grid preserves every "
            "original highlighted location."
        ),
        stimulus={
            "type": "memory_grid",
            "grid_size": grid_size,
            "memorize": locations,
            "presentation_ms": PRESENTATION_MS[difficulty],
            "instruction": (
                "Memorize the highlighted "
                "locations in the grid."
            ),
            "option_format": "memory_grid_json",
        },
        family_version=FAMILY_VERSION,
    )


def manipulate(sequence, operation):
    if operation == "reverse":
        return sequence[::-1]

    if operation == "ascending":
        return sorted(sequence)

    if operation == "descending":
        return sorted(sequence, reverse=True)

    if operation == "rotate_left":
        return sequence[1:] + sequence[:1]

    if operation == "reverse_rotate_left":
        reversed_sequence = sequence[::-1]

        return (
            reversed_sequence[1:]
            + reversed_sequence[:1]
        )

    raise ValueError(
        "Unknown memory operation."
    )


MANIPULATION_RULES = {
    1: ("reverse",),
    2: ("reverse", "ascending"),
    3: ("ascending", "descending"),
    4: ("reverse", "rotate_left"),
    5: ("reverse_rotate_left",),
}


MANIPULATION_LABELS = {
    "reverse": "Reverse the original sequence.",
    "ascending": "Arrange the digits from lowest to highest.",
    "descending": "Arrange the digits from highest to lowest.",
    "rotate_left": (
        "Move the first digit to the end, "
        "preserving the order of the others."
    ),
    "reverse_rotate_left": (
        "Reverse the original sequence, then "
        "move its first digit to the end."
    ),
}


def sequence_manipulation(difficulty, seed=None):
    family = "sequence_manipulation"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    operation = rng.choice(
        MANIPULATION_RULES[difficulty]
    )

    for _ in range(100):
        sequence = rng.sample(
            list(range(10)),
            difficulty + 3,
        )

        answer = manipulate(
            sequence, operation
        )

        if answer != sequence:
            break

    else:
        raise RuntimeError(
            "Unable to generate nontrivial "
            "memory transformation."
        )

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            MANIPULATION_LABELS[operation]
            + " Which sequence is correct?"
        ),
        correct_answer=encode_sequence(answer),
        distractors=sequence_distractors(
            answer, rng
        ),
        explanation=(
            "Original sequence: "
            + encode_sequence(sequence)
            + ". Transformed sequence: "
            + encode_sequence(answer)
            + "."
        ),
        stimulus={
            "type": "memory_manipulation",
            "memorize": sequence,
            "operation": operation,
            "presentation_ms": PRESENTATION_MS[difficulty],
            "instruction": (
                "Memorize the digits in their "
                "original order."
            ),
        },
        family_version=FAMILY_VERSION,
    )


def presentation_payload(question):
    stimulus = question["stimulus"]

    result = {
        "id": question["id"],
        "stage": "memorize",
        "type": stimulus["type"],
        "instruction": stimulus["instruction"],
        "presentation_ms": stimulus["presentation_ms"],
        "memorize": deepcopy(stimulus["memorize"]),
    }

    if "grid_size" in stimulus:
        result["grid_size"] = stimulus["grid_size"]

    return result


def response_payload(question):
    stimulus = question["stimulus"]

    result = {
        "id": question["id"],
        "stage": "respond",
        "domain": question["domain"],
        "family": question["family"],
        "difficulty": question["difficulty"],
        "prompt": question["prompt"],
        "options": deepcopy(question["options"]),
        "type": stimulus["type"],
    }

    if "grid_size" in stimulus:
        result["grid_size"] = stimulus["grid_size"]

    if "option_format" in stimulus:
        result["option_format"] = stimulus["option_format"]

    return result


def verify_question(question):
    stimulus = question["stimulus"]
    original = stimulus["memorize"]
    family = question["family"]

    if family == "sequence_recognition":
        expected = encode_sequence(original)

    elif family == "spatial_memory":
        assert len(original) == len(set(original))

        assert all(
            0 <= location < stimulus["grid_size"] ** 2
            for location in original
        )

        expected = encode_locations(original)

    elif family == "sequence_manipulation":
        operation = stimulus["operation"]

        if operation == "reverse":
            values = [
                original[index]
                for index in range(
                    len(original) - 1, -1, -1
                )
            ]

        elif operation == "ascending":
            values = [
                digit
                for digit in range(10)
                if digit in original
            ]

        elif operation == "descending":
            values = [
                digit
                for digit in range(9, -1, -1)
                if digit in original
            ]

        elif operation == "rotate_left":
            values = [
                original[(index + 1) % len(original)]
                for index in range(len(original))
            ]

        elif operation == "reverse_rotate_left":
            values = [
                original[
                    (len(original) - 2 - index)
                    % len(original)
                ]
                for index in range(len(original))
            ]

        else:
            raise AssertionError(
                "Unknown operation."
            )

        expected = encode_sequence(values)

    else:
        raise AssertionError(
            "Unknown memory family."
        )

    matches = [
        option["id"]
        for option in question["options"]
        if option["value"] == expected
    ]

    assert len(matches) == 1
    assert matches[0] == question["correct_option_id"]

    presentation = presentation_payload(question)
    response = response_payload(question)

    assert "options" not in presentation
    assert "correct_option_id" not in presentation
    assert "memorize" not in response
    assert "stimulus" not in response
    assert "correct_option_id" not in response
    assert "explanation" not in response
    assert "seed" not in response

    assert presentation["id"] == response["id"]

    return True


GENERATORS = {
    "sequence_recognition": sequence_recognition,
    "spatial_memory": spatial_memory,
    "sequence_manipulation": sequence_manipulation,
}


def generate_question(family, difficulty, seed=None):
    if family not in GENERATORS:
        raise ValueError(
            "Unknown working memory family."
        )

    return GENERATORS[family](difficulty, seed)


def run_tests():
    total = 0

    for family in GENERATORS:
        for difficulty in range(1, 6):
            prompts = set()
            positions = set()

            for index in range(2000):
                seed = f"memory-test-{index}"

                question = generate_question(
                    family, difficulty, seed
                )

                assert question == generate_question(
                    family, difficulty, seed
                )

                assert len(question["options"]) == 5

                assert len({
                    option["value"]
                    for option in question["options"]
                }) == 5

                assert verify_question(question)

                prompts.add(question["prompt_hash"])

                positions.add(
                    question["correct_option_id"]
                )

                total += 1

            assert positions == set("ABCDE")

            print(
                f"{family}, level {difficulty}: "
                f"2000 verified; "
                f"{len(prompts)} unique stimuli; "
                "PASSED"
            )

    assert total == 30000

    for family in GENERATORS:
        question = generate_question(
            family, 5, "negative-control"
        )

        question["correct_option_id"] = next(
            option["id"]
            for option in question["options"]
            if option["id"] != question["correct_option_id"]
        )

        try:
            verify_question(question)
        except AssertionError:
            print(
                f"{family}: incorrect answer-key "
                "detection PASSED"
            )
        else:
            raise AssertionError(
                "Incorrect memory answer accepted."
            )

    print("Presentation payload isolation: PASSED")
    print("Response payload isolation: PASSED")

    print()
    print("ALL 30,000 WORKING MEMORY TESTS PASSED")


if __name__ == "__main__":
    run_tests()

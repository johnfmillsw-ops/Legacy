
"""
Legacy Phase VII: Processing speed generators.

Experimental visual comparison and discrimination tasks.
Response timing is handled by the assessment session layer.
"""

import json

from cognitive_engine import (
    build_question,
    question_rng,
    create_seed,
)

FAMILY_VERSION = 1

SYMBOLS = (
    "circle",
    "square",
    "triangle",
    "diamond",
    "star",
    "cross",
)

COMPARISON_LENGTHS = {
    1: 4,
    2: 5,
    3: 6,
    4: 7,
    5: 8,
}


def encode(values):
    return json.dumps(
        values,
        separators=(",", ":"),
    )


def sequence_candidates(reference, population):
    candidates = set()

    for index, original in enumerate(reference):
        for replacement in population:
            if replacement == original:
                continue

            altered = list(reference)
            altered[index] = replacement

            candidates.add(encode(altered))

    return sorted(candidates)


def symbol_comparison(difficulty, seed=None):
    family = "symbol_comparison"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    reference = [
        rng.choice(SYMBOLS)
        for _ in range(
            COMPARISON_LENGTHS[difficulty]
        )
    ]

    answer = encode(reference)

    candidates = sequence_candidates(
        reference, SYMBOLS
    )

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "Which arrangement exactly matches "
            "the reference?"
        ),
        correct_answer=answer,
        distractors=rng.sample(candidates, 4),
        explanation=(
            "Every symbol must match the reference "
            "in both identity and position."
        ),
        stimulus={
            "type": "speed_symbol_comparison",
            "reference": reference,
            "option_format": "symbol_sequence_json",
            "timed": True,
        },
        family_version=FAMILY_VERSION,
    )


def visual_discrimination(difficulty, seed=None):
    family = "visual_discrimination"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    grid_size = difficulty + 2

    population = list(
        range(grid_size * grid_size)
    )

    count = grid_size + difficulty

    reference = sorted(
        rng.sample(population, count)
    )

    occupied = set(reference)

    candidates = set()

    for removed in reference:
        for added in population:
            if added in occupied:
                continue

            altered = sorted(
                (occupied - {removed}) | {added}
            )

            candidates.add(encode(altered))

    answer = encode(reference)

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "Which grid exactly matches "
            "the reference grid?"
        ),
        correct_answer=answer,
        distractors=rng.sample(
            sorted(candidates), 4
        ),
        explanation=(
            "The correct grid preserves every "
            "highlighted cell."
        ),
        stimulus={
            "type": "speed_visual_discrimination",
            "grid_size": grid_size,
            "reference": reference,
            "option_format": "speed_grid_json",
            "timed": True,
        },
        family_version=FAMILY_VERSION,
    )


def contains_pattern(sequence, target):
    length = len(target)

    return any(
        sequence[index:index + length] == target
        for index in range(
            len(sequence) - length + 1
        )
    )


def pattern_matching(difficulty, seed=None):
    family = "pattern_matching"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    target_length = difficulty + 2
    sequence_length = target_length + 4

    target = [
        rng.choice(SYMBOLS)
        for _ in range(target_length)
    ]

    # Build five sequences with identical lengths.
    # Only one may contain the complete target.

    candidates = set()

    for _ in range(500):
        sequence = [
            rng.choice(SYMBOLS)
            for _ in range(sequence_length)
        ]

        position = rng.randint(
            0, sequence_length - target_length
        )

        sequence[
            position:position + target_length
        ] = target

        altered = list(sequence)

        change_index = (
            position
            + rng.randrange(target_length)
        )

        altered[change_index] = rng.choice([
            symbol
            for symbol in SYMBOLS
            if symbol != altered[change_index]
        ])

        if not contains_pattern(altered, target):
            candidates.add(encode(altered))

        if len(candidates) >= 4:
            break

    if len(candidates) < 4:
        raise RuntimeError(
            "Insufficient pattern distractors."
        )

    correct = [
        rng.choice(SYMBOLS)
        for _ in range(sequence_length)
    ]

    position = rng.randint(
        0, sequence_length - target_length
    )

    correct[
        position:position + target_length
    ] = target

    answer = encode(correct)

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "Which arrangement contains the entire "
            "reference pattern in consecutive "
            "positions and in the same order?"
        ),
        correct_answer=answer,
        distractors=rng.sample(
            sorted(candidates), 4
        ),
        explanation=(
            "Only the correct arrangement contains "
            "the complete consecutive reference "
            "pattern in its original order."
        ),
        stimulus={
            "type": "speed_pattern_matching",
            "reference": target,
            "option_format": "symbol_sequence_json",
            "timed": True,
        },
        family_version=FAMILY_VERSION,
    )


def verify_question(question):
    family = question["family"]
    stimulus = question["stimulus"]
    reference = stimulus["reference"]

    options = [
        (
            option["id"],
            json.loads(option["value"]),
        )
        for option in question["options"]
    ]

    assert len(options) == 5

    assert len({
        encode(value)
        for _, value in options
    }) == 5

    assert stimulus["timed"] is True

    if family == "symbol_comparison":
        assert len(reference) == (
            COMPARISON_LENGTHS[
                question["difficulty"]
            ]
        )

        assert all(
            len(value) == len(reference)
            for _, value in options
        )

        matches = [
            option_id
            for option_id, value in options
            if all(
                left == right
                for left, right in zip(
                    reference, value
                )
            )
        ]

        for option_id, value in options:
            differences = sum(
                left != right
                for left, right in zip(
                    reference, value
                )
            )

            assert differences in (0, 1)

    elif family == "visual_discrimination":
        grid_size = stimulus["grid_size"]

        expected = set(reference)

        assert len(expected) == len(reference)

        matches = []

        for option_id, value in options:
            assert len(value) == len(reference)
            assert len(set(value)) == len(value)

            assert all(
                0 <= cell < grid_size ** 2
                for cell in value
            )

            difference = expected.symmetric_difference(
                set(value)
            )

            assert len(difference) in (0, 2)

            if not difference:
                matches.append(option_id)

    elif family == "pattern_matching":
        # Independently search for the pattern
        # using a symbol-by-symbol state scan.

        matches = []

        for option_id, value in options:
            assert len(value) == len(reference) + 4

            active = set()
            found = False

            for symbol in value:
                updated = set()

                if symbol == reference[0]:
                    updated.add(1)

                for position in active:
                    if position < len(reference):
                        if symbol == reference[position]:
                            updated.add(position + 1)

                if len(reference) in updated:
                    found = True

                active = updated

            if found:
                matches.append(option_id)

    else:
        raise AssertionError(
            "Unknown processing speed family."
        )

    assert len(matches) == 1

    assert matches[0] == (
        question["correct_option_id"]
    )

    return True


GENERATORS = {
    "symbol_comparison": symbol_comparison,
    "visual_discrimination": visual_discrimination,
    "pattern_matching": pattern_matching,
}


def generate_question(family, difficulty, seed=None):
    if family not in GENERATORS:
        raise ValueError(
            "Unknown processing speed family."
        )

    return GENERATORS[family](difficulty, seed)


def run_tests():
    total = 0

    for family in GENERATORS:
        for difficulty in range(1, 6):
            prompts = set()
            positions = set()

            for index in range(2000):
                seed = f"speed-test-{index}"

                question = generate_question(
                    family, difficulty, seed
                )

                assert question == generate_question(
                    family, difficulty, seed
                )

                assert verify_question(question)

                prompts.add(
                    question["prompt_hash"]
                )

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
                "Incorrect processing speed "
                "answer accepted."
            )

    print()
    print("ALL 30,000 PROCESSING SPEED TESTS PASSED")


if __name__ == "__main__":
    run_tests()

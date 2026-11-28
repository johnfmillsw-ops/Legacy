"""
Legacy Phase VII: Abstract visual matrices.

Original procedural visual reasoning items.
Structured visual data for future SVG rendering.
"""

import json
from itertools import product

from cognitive_engine import (
    build_question,
    question_rng,
    create_seed,
)

FAMILY_VERSION = 1

SHAPES = (
    "triangle",
    "square",
    "pentagon",
    "arrow",
    "diamond",
)

FILLS = (
    "outline",
    "solid",
)

ATTRIBUTES = (
    "shape",
    "quantity",
    "orientation",
    "fill",
)

MODULI = {
    "shape": len(SHAPES),
    "quantity": 4,
    "orientation": 4,
    "fill": 2,
}


def encode_cell(cell):
    return json.dumps(
        cell,
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_cell(values):
    return {
        "shape": SHAPES[values["shape"]],
        "quantity": values["quantity"] + 1,
        "orientation": values["orientation"] * 90,
        "fill": FILLS[values["fill"]],
    }


def generate_matrix(difficulty, seed=None):
    family = "abstract_matrices"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family,
        difficulty,
        seed,
        FAMILY_VERSION,
    )

    bases = {
        key: rng.randrange(MODULI[key])
        for key in ATTRIBUTES
    }

    rules = {
        key: (0, 0)
        for key in ATTRIBUTES
    }

    if difficulty == 1:
        key = rng.choice(("shape", "quantity", "fill"))
        axis = rng.randrange(2)

        rules[key] = (
            (1, 0) if axis == 0 else (0, 1)
        )

    elif difficulty == 2:
        rules["shape"] = (
            rng.choice((1, 2, 3, 4)), 0
        )

        rules["quantity"] = (
            0, rng.choice((1, 3))
        )

    elif difficulty == 3:
        rules["shape"] = (
            rng.choice((1, 2, 3, 4)), 0
        )

        rules["quantity"] = (
            0, rng.choice((1, 3))
        )

        rules["fill"] = (1, 1)

    elif difficulty == 4:
        bases["shape"] = SHAPES.index("arrow")

        rules["quantity"] = (
            rng.choice((1, 3)),
            rng.choice((1, 3)),
        )

        rules["orientation"] = (
            rng.choice((1, 3)),
            rng.choice((1, 3)),
        )

        rules["fill"] = (1, 1)

    else:
        rules["shape"] = (
            rng.choice((1, 2, 3, 4)),
            rng.choice((1, 2, 3, 4)),
        )

        rules["quantity"] = (
            rng.choice((1, 3)),
            rng.choice((1, 3)),
        )

        rules["fill"] = rng.choice(
            ((1, 0), (0, 1), (1, 1))
        )

    # Orientation remains constant unless the
    # shape is always an asymmetric arrow.
    if difficulty != 4:
        bases["orientation"] = 0

    def values_at(row, column):
        return {
            key: (
                bases[key]
                + rules[key][0] * row
                + rules[key][1] * column
            ) % MODULI[key]
            for key in ATTRIBUTES
        }

    cells = [
        decode_cell(values_at(row, column))
        for row in range(3)
        for column in range(3)
    ]

    answer_values = values_at(2, 2)
    answer = encode_cell(cells[-1])

    active = [
        key
        for key in ATTRIBUTES
        if rules[key] != (0, 0)
    ]

    candidates = set()

    for key in active:
        for offset in range(1, MODULI[key]):
            altered = dict(answer_values)

            altered[key] = (
                altered[key] + offset
            ) % MODULI[key]

            candidates.add(
                encode_cell(decode_cell(altered))
            )

    # If fewer than four distractors exist,
    # vary another visible attribute.
    if len(candidates) < 4:
        for key in ("shape", "quantity", "fill"):
            for offset in range(1, MODULI[key]):
                altered = dict(answer_values)

                altered[key] = (
                    altered[key] + offset
                ) % MODULI[key]

                candidates.add(
                    encode_cell(decode_cell(altered))
                )

    candidates.discard(answer)

    distractors = sorted(candidates)
    rng.shuffle(distractors)

    stimulus = {
        "type": "visual_matrix",
        "rows": 3,
        "columns": 3,
        "cells": cells[:-1] + [None],
        "option_format": "visual_cell_json",
    }

    explanation_parts = []

    for key in active:
        row_step, column_step = rules[key]

        explanation_parts.append(
            f"{key}: row step {row_step}, "
            f"column step {column_step}, "
            f"cycle length {MODULI[key]}"
        )

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "Which visual element completes "
            "the matrix?"
        ),
        correct_answer=answer,
        distractors=distractors[:4],
        explanation="; ".join(explanation_parts),
        stimulus=stimulus,
        family_version=FAMILY_VERSION,
    )


def infer_attribute(values, modulus):
    """
    Independently infer all compatible cyclic rules
    from the eight visible matrix cells.
    """

    predictions = set()

    for base, row_step, column_step in product(
        range(modulus),
        range(modulus),
        range(modulus),
    ):
        predicted = [
            (
                base
                + row_step * (i // 3)
                + column_step * (i % 3)
            ) % modulus
            for i in range(9)
        ]

        if predicted[:8] == values:
            predictions.add(predicted[8])

    if len(predictions) != 1:
        raise AssertionError(
            "Matrix attribute has no unique "
            "solution within the supported rule class."
        )

    return predictions.pop()


def encode_attributes(cell):
    return {
        "shape": SHAPES.index(cell["shape"]),
        "quantity": cell["quantity"] - 1,
        "orientation": cell["orientation"] // 90,
        "fill": FILLS.index(cell["fill"]),
    }


def verify_matrix(question):
    stimulus = question["stimulus"]
    cells = stimulus["cells"]

    assert len(cells) == 9
    assert cells[-1] is None
    assert all(cell is not None for cell in cells[:8])

    visible = [
        encode_attributes(cell)
        for cell in cells[:8]
    ]

    expected = {}

    for key in ATTRIBUTES:
        expected[key] = infer_attribute(
            [cell[key] for cell in visible],
            MODULI[key],
        )

    expected_cell = decode_cell(expected)

    matches = [
        option["id"]
        for option in question["options"]
        if json.loads(option["value"]) == expected_cell
    ]

    assert len(matches) == 1
    assert matches[0] == question["correct_option_id"]

    return True


def run_tests():
    total = 0

    for difficulty in range(1, 6):
        prompts = set()
        positions = set()

        for index in range(2000):
            seed = f"matrix-test-{index}"

            question = generate_matrix(
                difficulty,
                seed,
            )

            assert question == generate_matrix(
                difficulty,
                seed,
            )

            assert len(question["options"]) == 5

            assert len({
                option["value"]
                for option in question["options"]
            }) == 5

            assert verify_matrix(question)

            prompts.add(question["prompt_hash"])

            positions.add(
                question["correct_option_id"]
            )

            total += 1

        assert positions == set("ABCDE")

        print(
            f"Level {difficulty}: "
            f"2000 matrices verified; "
            f"{len(prompts)} unique visual prompts; "
            "PASSED"
        )

    assert total == 10000

    question = generate_matrix(
        5, "negative-control"
    )

    question["correct_option_id"] = next(
        option["id"]
        for option in question["options"]
        if option["id"] != question["correct_option_id"]
    )

    try:
        verify_matrix(question)
    except AssertionError:
        print("Incorrect answer-key detection: PASSED")
    else:
        raise AssertionError(
            "Incorrect matrix answer accepted."
        )

    print()
    print("ALL 10,000 MATRIX VERIFICATIONS PASSED")


if __name__ == "__main__":
    run_tests()

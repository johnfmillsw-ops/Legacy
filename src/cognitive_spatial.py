
"""
Legacy Phase VII: Visual-spatial reasoning.

Procedural geometric objects and spatial transformations.
Original experimental cognitive items.
"""

import json

from cognitive_engine import (
    build_question,
    question_rng,
    create_seed,
)

FAMILY_VERSION = 1

DIRECTIONS = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
    "northeast": (1, -1),
    "northwest": (-1, -1),
    "southeast": (1, 1),
    "southwest": (-1, 1),
}


def normalize(points):
    min_x = min(x for x, y in points)
    min_y = min(y for x, y in points)

    return tuple(sorted(
        (x - min_x, y - min_y)
        for x, y in points
    ))


def encode(points):
    return json.dumps(
        normalize(points),
        separators=(",", ":"),
    )


def rotate(points, turns):
    result = tuple(points)

    for _ in range(turns % 4):
        result = tuple(
            (-y, x)
            for x, y in result
        )

    return normalize(result)


def reflect(points):
    return normalize(
        [(-x, y) for x, y in points]
    )


def orientations(points):
    return {
        rotate(shape, turns)
        for shape in (points, reflect(points))
        for turns in range(4)
    }


def generate_shape(size, rng):
    for _ in range(500):
        points = {(0, 0)}

        while len(points) < size:
            x, y = rng.choice(sorted(points))

            dx, dy = rng.choice(
                ((1, 0), (-1, 0), (0, 1), (0, -1))
            )

            points.add((x + dx, y + dy))

        shape = normalize(points)

        width = max(x for x, y in shape) + 1
        height = max(y for x, y in shape) + 1

        if width > 7 or height > 7:
            continue

        if len(orientations(shape)) == 8:
            return shape

    raise RuntimeError(
        "Unable to generate asymmetric shape."
    )


def visual_question(
    family,
    difficulty,
    seed,
    rng,
    shape,
    answer,
    operations,
    prompt,
):
    candidates = sorted(
        orientations(shape) - {answer}
    )

    distractors = rng.sample(candidates, 4)

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=prompt,
        correct_answer=encode(answer),
        distractors=[
            encode(candidate)
            for candidate in distractors
        ],
        explanation=(
            "Apply these transformations in order: "
            + ", ".join(operations)
            + "."
        ),
        stimulus={
            "type": "spatial_object",
            "points": [list(point) for point in shape],
            "operations": operations,
            "option_format": "coordinate_shape_json",
        },
        family_version=FAMILY_VERSION,
    )


def mental_rotation(difficulty, seed=None):
    family = "mental_rotation"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    shape = generate_shape(
        difficulty + 4, rng
    )

    turns = rng.choice((1, 2, 3))

    degrees = turns * 90

    answer = rotate(shape, turns)

    operations = [
        f"rotate_{degrees}_clockwise"
    ]

    return visual_question(
        family,
        difficulty,
        seed,
        rng,
        shape,
        answer,
        operations,
        (
            "Which object results from rotating "
            f"the original {degrees} degrees clockwise?"
        ),
    )


def spatial_transformation(difficulty, seed=None):
    family = "spatial_transformation"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    shape = generate_shape(
        difficulty + 4, rng
    )

    answer = shape
    operations = []

    for _ in range(difficulty + 1):
        operation = rng.choice((
            "rotate_90_clockwise",
            "rotate_180_clockwise",
            "rotate_270_clockwise",
            "reflect_horizontal",
        ))

        operations.append(operation)

        if operation == "reflect_horizontal":
            answer = reflect(answer)
        else:
            degrees = int(operation.split("_")[1])
            answer = rotate(answer, degrees // 90)

    labels = {
        "rotate_90_clockwise":
            "Rotate 90 degrees clockwise",
        "rotate_180_clockwise":
            "Rotate 180 degrees clockwise",
        "rotate_270_clockwise":
            "Rotate 270 degrees clockwise",
        "reflect_horizontal":
            "Mirror left to right",
    }

    prompt = (
        "Apply these operations in order: "
        + "; ".join(
            labels[operation]
            for operation in operations
        )
        + ". Which object results?"
    )

    return visual_question(
        family,
        difficulty,
        seed,
        rng,
        shape,
        answer,
        operations,
        prompt,
    )


def direction_name(x, y):
    horizontal = (
        "east" if x > 0
        else "west" if x < 0
        else ""
    )

    vertical = (
        "south" if y > 0
        else "north" if y < 0
        else ""
    )

    return vertical + horizontal or "starting point"


def spatial_relationships(difficulty, seed=None):
    family = "spatial_relationships"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    moves = []
    x = y = 0

    for _ in range(difficulty + 2):
        direction = rng.choice(
            ("north", "south", "east", "west")
        )

        distance = rng.randint(
            1, difficulty + 3
        )

        dx, dy = DIRECTIONS[direction]

        x += dx * distance
        y += dy * distance

        moves.append({
            "direction": direction,
            "distance": distance,
        })

    answer = direction_name(x, y)

    candidates = [
        name
        for name in list(DIRECTIONS) + ["starting point"]
        if name != answer
    ]

    prompt = (
        "Start at point A. "
        + " ".join(
            f"Move {move['distance']} units "
            f"{move['direction']}."
            for move in moves
        )
        + " In which direction is your final position "
        "relative to point A?"
    )

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=prompt,
        correct_answer=answer,
        distractors=rng.sample(candidates, 4),
        explanation=(
            f"Net displacement: {x} horizontal units "
            f"and {y} vertical units, using east and "
            "south as positive directions."
        ),
        stimulus={
            "type": "spatial_navigation",
            "moves": moves,
        },
        family_version=FAMILY_VERSION,
    )


def verify_visual(question):
    stimulus = question["stimulus"]

    points = [
        complex(x, y)
        for x, y in stimulus["points"]
    ]

    # Independent transformation implementation
    # using complex-number multiplication.

    for operation in stimulus["operations"]:
        if operation == "reflect_horizontal":
            points = [
                -point.conjugate()
                for point in points
            ]
        else:
            factor = {
                "rotate_90_clockwise": 1j,
                "rotate_180_clockwise": -1,
                "rotate_270_clockwise": -1j,
            }[operation]

            points = [
                point * factor
                for point in points
            ]

    min_x = min(point.real for point in points)
    min_y = min(point.imag for point in points)

    expected = sorted(
        [
            int(point.real - min_x),
            int(point.imag - min_y),
        ]
        for point in points
    )

    matches = [
        option["id"]
        for option in question["options"]
        if json.loads(option["value"]) == expected
    ]

    assert len(matches) == 1
    assert matches[0] == question["correct_option_id"]

    decoded = [
        tuple(
            tuple(point)
            for point in json.loads(option["value"])
        )
        for option in question["options"]
    ]

    assert len(set(decoded)) == 5

    assert all(
        len(points) == len(expected)
        for points in decoded
    )


def verify_navigation(question):
    import re

    moves = re.findall(
        r"Move (\d+) units "
        r"(north|south|east|west)\.",
        question["prompt"],
    )

    assert len(moves) == question["difficulty"] + 2

    totals = {
        name: 0
        for name in ("north", "south", "east", "west")
    }

    for distance, direction in moves:
        totals[direction] += int(distance)

    vertical = totals["north"] - totals["south"]
    horizontal = totals["east"] - totals["west"]

    sign = lambda value: (value > 0) - (value < 0)

    expected = {
        (0, 0): "starting point",
        (1, 0): "north",
        (-1, 0): "south",
        (0, 1): "east",
        (0, -1): "west",
        (1, 1): "northeast",
        (1, -1): "northwest",
        (-1, 1): "southeast",
        (-1, -1): "southwest",
    }[(sign(vertical), sign(horizontal))]

    matches = [
        option["id"]
        for option in question["options"]
        if option["value"] == expected
    ]

    assert len(matches) == 1
    assert matches[0] == question["correct_option_id"]


GENERATORS = {
    "mental_rotation": mental_rotation,
    "spatial_transformation": spatial_transformation,
    "spatial_relationships": spatial_relationships,
}

VERIFIERS = {
    "mental_rotation": verify_visual,
    "spatial_transformation": verify_visual,
    "spatial_relationships": verify_navigation,
}


def generate_question(family, difficulty, seed=None):
    if family not in GENERATORS:
        raise ValueError("Unknown spatial family.")

    return GENERATORS[family](difficulty, seed)


def run_tests():
    total = 0

    for family in GENERATORS:
        for difficulty in range(1, 6):
            prompts = set()
            positions = set()

            for index in range(2000):
                seed = f"spatial-test-{index}"

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

                VERIFIERS[family](question)

                prompts.add(question["prompt_hash"])

                positions.add(
                    question["correct_option_id"]
                )

                total += 1

            assert positions == set("ABCDE")

            print(
                f"{family}, level {difficulty}: "
                f"2000 verified; "
                f"{len(prompts)} unique prompts; "
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
            VERIFIERS[family](question)
        except AssertionError:
            print(
                f"{family}: incorrect answer-key "
                "detection PASSED"
            )
        else:
            raise AssertionError(
                "Incorrect spatial answer accepted."
            )

    print()
    print("ALL 30,000 SPATIAL REASONING TESTS PASSED")


if __name__ == "__main__":
    run_tests()

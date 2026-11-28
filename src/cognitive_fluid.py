
"""
Legacy Phase VII: Fluid reasoning generators.

Symbolic sequences and deductive reasoning.
Original experimental cognitive items.
"""

from itertools import permutations

from cognitive_engine import (
    build_question,
    question_rng,
    create_seed,
)

FAMILY_VERSION = 1

SYMBOLS = (
    "A", "B", "C", "D", "E",
    "F", "G", "H", "J", "K",
    "L", "M", "N", "P", "R",
)


def transform(sequence, operation):
    if operation == "left":
        return sequence[1:] + sequence[:1]

    if operation == "right":
        return sequence[-1:] + sequence[:-1]

    if operation == "reverse":
        return sequence[::-1]

    if operation == "swap_first":
        return (
            sequence[1:2]
            + sequence[:1]
            + sequence[2:]
        )

    if operation == "swap_last":
        return (
            sequence[:-2]
            + sequence[-1:]
            + sequence[-2:-1]
        )

    raise ValueError("Unknown transformation.")


OPERATIONS = (
    "left",
    "right",
    "reverse",
    "swap_first",
    "swap_last",
)


def operation_rules(difficulty):
    if difficulty == 1:
        return [
            (operation,)
            for operation in ("left", "right")
        ]

    if difficulty == 2:
        return [
            (operation,)
            for operation in OPERATIONS
        ]

    if difficulty == 3:
        return list(permutations(OPERATIONS, 2))

    if difficulty == 4:
        return list(permutations(OPERATIONS, 3))

    if difficulty == 5:
        return list(permutations(OPERATIONS, 4))

    raise ValueError("Invalid difficulty.")


def predict_sequence(visible, rules):
    predictions = set()

    for rule in rules:
        valid = all(
            transform(
                visible[index],
                rule[index % len(rule)],
            ) == visible[index + 1]
            for index in range(len(visible) - 1)
        )

        if valid:
            predictions.add(
                transform(
                    visible[-1],
                    rule[(len(visible) - 1) % len(rule)],
                )
            )

    return predictions


def logical_sequences(difficulty, seed=None):
    family = "logical_sequences"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    rules = operation_rules(difficulty)
    rule = rng.choice(rules)

    length = 4 if difficulty <= 2 else 5

    initial = "".join(
        rng.sample(SYMBOLS, length)
    )

    visible = [initial]

    transitions = len(rule) * 2

    for index in range(transitions):
        visible.append(
            transform(
                visible[-1],
                rule[index % len(rule)],
            )
        )

    answer = transform(
        visible[-1],
        rule[transitions % len(rule)],
    )

    predictions = predict_sequence(
        visible, rules
    )

    if predictions != {answer}:
        raise ValueError(
            "Ambiguous symbolic sequence."
        )

    candidates = [
        "".join(value)
        for value in permutations(initial)
        if "".join(value) != answer
    ]

    distractors = rng.sample(candidates, 4)

    stimulus = {
        "type": "symbol_sequence",
        "terms": visible,
        "missing": True,
    }

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "The same transformation or repeating "
            "cycle of transformations is applied "
            "to the symbols. Which arrangement "
            "comes next?"
        ),
        correct_answer=answer,
        distractors=distractors,
        explanation=(
            "The repeating transformations are: "
            + ", ".join(rule)
            + "."
        ),
        stimulus=stimulus,
        family_version=FAMILY_VERSION,
    )


def reachable(edges, start, target):
    """
    Independently determine whether a directed
    path connects two entities.
    """

    pending = [start]
    visited = set()

    while pending:
        current = pending.pop()

        if current == target:
            return True

        if current in visited:
            continue

        visited.add(current)

        pending.extend(
            right
            for left, right in edges
            if left == current
            and right not in visited
        )

    return False


def deductive_reasoning(difficulty, seed=None):
    family = "deductive_reasoning"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    chain_length = difficulty + 2

    entities = rng.sample(
        SYMBOLS, chain_length + 2
    )

    chain = entities[:chain_length]
    unrelated = entities[chain_length:]

    edges = list(
        zip(chain, chain[1:])
    )

    edges.append(
        (unrelated[0], unrelated[1])
    )

    if difficulty >= 3:
        edges.append(
            (chain[1], unrelated[1])
        )

    rng.shuffle(edges)

    answer_pair = (chain[0], chain[-1])

    direct_edges = set(edges)

    assert answer_pair not in direct_edges

    false_pairs = [
        (left, right)
        for left in entities
        for right in entities
        if left != right
        and not reachable(edges, left, right)
    ]

    selected_false = rng.sample(
        false_pairs, 4
    )

    def statement(pair):
        return (
            f"{pair[0]} is taller than {pair[1]}."
        )

    premises = [
        statement(edge)
        for edge in edges
    ]

    stimulus = {
        "type": "deductive_premises",
        "premises": premises,
    }

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "Assume every stated relationship is "
            "true. Which conclusion must follow?"
        ),
        correct_answer=statement(answer_pair),
        distractors=[
            statement(pair)
            for pair in selected_false
        ],
        explanation=(
            "The chain of relationships is "
            + " > ".join(chain)
            + ". Therefore "
            + statement(answer_pair)
        ),
        stimulus=stimulus,
        family_version=FAMILY_VERSION,
    )


def verify_sequence(question):
    visible = question["stimulus"]["terms"]

    predictions = predict_sequence(
        visible,
        operation_rules(question["difficulty"]),
    )

    assert len(predictions) == 1

    matches = [
        option["id"]
        for option in question["options"]
        if option["value"] in predictions
    ]

    assert len(matches) == 1
    assert matches[0] == question["correct_option_id"]


def parse_relationship(statement):
    words = statement.rstrip(".").split()

    assert len(words) == 5
    assert words[1:4] == ["is", "taller", "than"]

    return words[0], words[4]


def verify_deduction(question):
    edges = [
        parse_relationship(statement)
        for statement in question["stimulus"]["premises"]
    ]

    # Compute transitive closure independently
    # of the generator's graph traversal.

    closure = set(edges)

    while True:
        expanded = closure | {
            (left, end)
            for left, middle in closure
            for start, end in closure
            if middle == start
        }

        if expanded == closure:
            break

        closure = expanded

    assert all(
        left != right
        for left, right in closure
    )

    matches = [
        option["id"]
        for option in question["options"]
        if parse_relationship(
            option["value"]
        ) in closure
    ]

    assert len(matches) == 1
    assert matches[0] == question["correct_option_id"]


GENERATORS = {
    "logical_sequences": logical_sequences,
    "deductive_reasoning": deductive_reasoning,
}

VERIFIERS = {
    "logical_sequences": verify_sequence,
    "deductive_reasoning": verify_deduction,
}


def generate_question(family, difficulty, seed=None):
    if family not in GENERATORS:
        raise ValueError("Unknown fluid reasoning family.")

    return GENERATORS[family](difficulty, seed)


def run_tests():
    total = 0

    for family in GENERATORS:
        for difficulty in range(1, 6):
            prompts = set()
            positions = set()

            for index in range(2000):
                seed = f"fluid-test-{index}"

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

    assert total == 20000

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
                "Incorrect answer accepted."
            )

    print()
    print("ALL 20,000 FLUID REASONING TESTS PASSED")


if __name__ == "__main__":
    run_tests()

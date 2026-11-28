
"""
Legacy Phase VII: Verbal comprehension engine.

Bank-backed experimental verbal reasoning questions.
"""

from cognitive_engine import (
    build_question,
    question_rng,
    create_seed,
)

from cognitive_verbal_bank import (
    BANK_VERSION,
    RELATIONSHIPS,
    SYNONYMS,
    ANTONYMS,
    CATEGORIES,
)

FAMILY_VERSION = 1

ANALOGY_LEVELS = {
    1: ("young_of", "object_function"),
    2: ("material_product", "young_of"),
    3: ("instrument_measurement", "object_function"),
    4: ("professional_field", "instrument_measurement"),
    5: ("professional_field", "material_product"),
}

CATEGORY_LEVELS = {
    1: ("mammals", "birds"),
    2: ("metals", "musical_instruments"),
    3: ("geometric_shapes", "units_of_length"),
    4: ("chemical_elements", "units_of_time"),
    5: ("literary_forms", "logical_connectives"),
}

RELATION_LABELS = {
    "young_of": "young animal and adult animal",
    "instrument_measurement": "instrument and measured property",
    "professional_field": "specialist and field of study",
    "material_product": "material and resulting product",
    "object_function": "object and its function",
}


def verbal_analogies(difficulty, seed=None):
    family = "verbal_analogies"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    relation = rng.choice(
        ANALOGY_LEVELS[difficulty]
    )

    pairs = RELATIONSHIPS[relation]

    first, second = rng.sample(pairs, 2)

    reverse = difficulty >= 4 and rng.choice(
        (True, False)
    )

    if reverse:
        first = first[::-1]
        second = second[::-1]

    a, b = first
    c, answer = second

    candidates = sorted({
        pair[0 if reverse else 1]
        for pair in pairs
        if pair[0 if reverse else 1] != answer
    })

    distractors = rng.sample(candidates, 4)

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            f"{a.capitalize()} is to {b} "
            f"as {c} is to what?"
        ),
        correct_answer=answer,
        distractors=distractors,
        explanation=(
            f"The relationship is "
            f"{RELATION_LABELS[relation]}. "
            f"{a} relates to {b} in the same "
            f"direction as {c} relates to {answer}."
        ),
        stimulus={
            "type": "verbal_analogy",
            "first": [a, b],
            "second": c,
        },
        family_version=FAMILY_VERSION,
    )


def semantic_relationships(difficulty, seed=None):
    family = "semantic_relationships"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    mode = rng.choice(("synonym", "antonym"))

    bank = (
        SYNONYMS if mode == "synonym"
        else ANTONYMS
    )

    pairs = bank[difficulty]

    word, answer = rng.choice(pairs)

    candidates = sorted({
        right
        for left, right in pairs
        if right != answer
        and right != word
    })

    distractors = rng.sample(candidates, 4)

    instruction = (
        "closest in meaning"
        if mode == "synonym"
        else "most opposite in meaning"
    )

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            f"Which word is {instruction} "
            f"to '{word}'?"
        ),
        correct_answer=answer,
        distractors=distractors,
        explanation=(
            f"'{answer}' is the intended "
            f"{mode} of '{word}' in this item."
        ),
        stimulus={
            "type": "semantic_relationship",
            "word": word,
            "relationship": mode,
        },
        family_version=FAMILY_VERSION,
    )


def concept_classification(difficulty, seed=None):
    family = "concept_classification"

    if seed is None:
        seed = create_seed()

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    category = rng.choice(
        CATEGORY_LEVELS[difficulty]
    )

    members = CATEGORIES[category]

    distractors = rng.sample(
        list(members), 4
    )

    # Exclude known overlapping categories.
    excluded_categories = {
        "metals": {"chemical_elements"},
        "chemical_elements": {"metals"},
    }

    excluded = excluded_categories.get(
        category, set()
    )

    outsiders = sorted({
        word
        for other_category, words in CATEGORIES.items()
        if other_category != category
        and other_category not in excluded
        for word in words
        if word not in members
    })

    answer = rng.choice(outsiders)

    label = category.replace("_", " ")

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=(
            "Which of these does NOT belong "
            f"to the category '{label}'?"
        ),
        correct_answer=answer,
        distractors=distractors,
        explanation=(
            f"The other four options belong "
            f"to the category '{label}'. "
            f"'{answer}' does not."
        ),
        stimulus={
            "type": "concept_classification",
            "category": category,
        },
        family_version=FAMILY_VERSION,
    )


def verify_analogy(question):
    stimulus = question["stimulus"]

    first = tuple(stimulus["first"])
    second = stimulus["second"]

    expected = set()

    for pairs in RELATIONSHIPS.values():
        for reverse in (False, True):
            oriented = [
                pair[::-1] if reverse else pair
                for pair in pairs
            ]

            if first in oriented:
                expected.update(
                    right
                    for left, right in oriented
                    if left == second
                )

    assert len(expected) == 1

    return expected


def verify_semantic(question):
    stimulus = question["stimulus"]

    word = stimulus["word"]
    mode = stimulus["relationship"]

    bank = (
        SYNONYMS if mode == "synonym"
        else ANTONYMS
    )

    expected = set()

    for pairs in bank.values():
        for left, right in pairs:
            if left == word:
                expected.add(right)

            if right == word:
                expected.add(left)

    assert expected

    return expected


def verify_classification(question):
    category = question["stimulus"]["category"]

    members = set(CATEGORIES[category])

    return {
        option["value"]
        for option in question["options"]
        if option["value"] not in members
    }


GENERATORS = {
    "verbal_analogies": verbal_analogies,
    "semantic_relationships": semantic_relationships,
    "concept_classification": concept_classification,
}

VERIFIERS = {
    "verbal_analogies": verify_analogy,
    "semantic_relationships": verify_semantic,
    "concept_classification": verify_classification,
}


def generate_question(family, difficulty, seed=None):
    if family not in GENERATORS:
        raise ValueError("Unknown verbal family.")

    return GENERATORS[family](difficulty, seed)


def verify_question(question):
    expected = VERIFIERS[
        question["family"]
    ](question)

    matches = [
        option["id"]
        for option in question["options"]
        if option["value"] in expected
    ]

    assert len(matches) == 1, (
        "Multiple or missing bank-supported answers."
    )

    assert matches[0] == question["correct_option_id"]

    return True


def run_tests():
    total = 0

    print("Verbal bank version:", BANK_VERSION)
    print()

    for family in GENERATORS:
        for difficulty in range(1, 6):
            prompts = set()
            content = set()
            positions = set()

            for index in range(2000):
                seed = f"verbal-test-{index}"

                question = generate_question(
                    family, difficulty, seed
                )

                assert question == generate_question(
                    family, difficulty, seed
                )

                assert len(question["options"]) == 5

                assert len({
                    option["value"].casefold()
                    for option in question["options"]
                }) == 5

                assert verify_question(question)

                prompts.add(question["prompt_hash"])
                content.add(question["content_hash"])

                positions.add(
                    question["correct_option_id"]
                )

                total += 1

            assert positions == set("ABCDE")

            print(
                f"{family}, level {difficulty}: "
                f"2000 verified; "
                f"{len(prompts)} unique prompts; "
                f"{len(content)} unique content hashes; "
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
                "Incorrect verbal answer accepted."
            )

    print()
    print("ALL 30,000 VERBAL ENGINE TESTS PASSED")


if __name__ == "__main__":
    run_tests()

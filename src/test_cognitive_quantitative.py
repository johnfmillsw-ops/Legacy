
"""
Independent verification of quantitative cognitive items.

Calculates answers from displayed question text rather
than trusting generator variables or stored explanations.
"""

import re

from fractions import Fraction

from cognitive_quantitative import (
    generate_question,
    GENERATORS,
)


def require_match(pattern, text):
    match = re.fullmatch(pattern, text)

    if match is None:
        raise AssertionError(
            "Unexpected question format: " + text
        )

    return tuple(int(value) for value in match.groups())


def solve_sequence(prompt, difficulty):
    prefix = (
        "Identify the intended numerical pattern. "
        "Which number comes next? "
    )

    assert prompt.startswith(prefix)

    text = prompt[len(prefix):]
    assert text.endswith(", ?")

    terms = [
        int(value)
        for value in text[:-3].split(", ")
    ]

    assert len(terms) == 6

    differences = [
        b - a
        for a, b in zip(terms, terms[1:])
    ]

    if difficulty == 1:
        assert len(set(differences)) == 1

        return terms[-1] + differences[0]

    if difficulty == 2:
        ratios = [
            Fraction(b, a)
            for a, b in zip(terms, terms[1:])
        ]

        assert len(set(ratios)) == 1

        return terms[-1] * ratios[0]

    if difficulty == 3:
        second_differences = [
            b - a
            for a, b in zip(
                differences, differences[1:]
            )
        ]

        assert len(set(second_differences)) == 1

        return (
            terms[-1]
            + differences[-1]
            + second_differences[0]
        )

    if difficulty == 4:
        ratios = [
            Fraction(terms[i + 1], terms[i])
            for i in (0, 2, 4)
        ]

        additions = [
            terms[i + 1] - terms[i]
            for i in (1, 3)
        ]

        assert len(set(ratios)) == 1
        assert len(set(additions)) == 1

        return terms[-1] + additions[0]

    if difficulty == 5:
        odd = terms[::2]
        even = terms[1::2]

        assert odd[1] - odd[0] == odd[2] - odd[1]
        assert even[1] - even[0] == even[2] - even[1]

        return odd[-1] + odd[1] - odd[0]

    raise AssertionError("Unsupported difficulty.")


def solve_relationship(prompt, difficulty):
    if difficulty == 1:
        quantity, cost, target = require_match(
            r"(\d+) identical items cost \$(\d+)\. "
            r"At the same unit price, how much do "
            r"(\d+) items cost in dollars\?",
            prompt,
        )

        return Fraction(cost, quantity) * target

    if difficulty == 2:
        workers, hours, target = require_match(
            r"(\d+) workers complete a task in "
            r"(\d+) hours\. "
            r"How many hours would (\d+) "
            r"workers need, assuming identical constant "
            r"rates and no interference\?",
            prompt,
        )

        return Fraction(workers * hours, target)

    if difficulty == 3:
        rate_a, rate_b, hours = require_match(
            r"Machine A produces (\d+) units per hour\. "
            r"Machine B produces (\d+) units per hour\. "
            r"How many units do they produce together "
            r"in (\d+) hours at constant rates\?",
            prompt,
        )

        return rate_a * hours + rate_b * hours

    if difficulty == 4:
        original, increase, decrease = require_match(
            r"A value of (\d+) increases by "
            r"(\d+)%, then the resulting value "
            r"decreases by (\d+)%\. "
            r"What is the final value\?",
            prompt,
        )

        return (
            Fraction(original)
            * Fraction(100 + increase, 100)
            * Fraction(100 - decrease, 100)
        )

    if difficulty == 5:
        count_a, value_a, count_b, value_b = require_match(
            r"Group A contains (\d+) measurements "
            r"with an average of (\d+)\. "
            r"Group B contains (\d+) measurements "
            r"with an average of (\d+)\. "
            r"What is the average of all measurements "
            r"combined\?",
            prompt,
        )

        return Fraction(
            count_a * value_a + count_b * value_b,
            count_a + count_b,
        )

    raise AssertionError("Unsupported difficulty.")


def solve_logic(prompt, difficulty):
    if difficulty == 1:
        addition, total = require_match(
            r"A number plus (\d+) equals (\d+)\. "
            r"What is the number\?",
            prompt,
        )

        return total - addition

    if difficulty == 2:
        multiplier, addition, total = require_match(
            r"A number multiplied by (\d+), then "
            r"increased by (\d+), equals (\d+)\. "
            r"What is the number\?",
            prompt,
        )

        return Fraction(
            total - addition, multiplier
        )

    if difficulty == 3:
        match = re.fullmatch(
            r"Solve for x: (\d+)x \+ (\d+) "
            r"= (\d+)x ([+-]) (\d+)",
            prompt,
        )

        assert match is not None, prompt

        a, b, c, sign, right = match.groups()

        a, b, c, right = map(
            int, (a, b, c, right)
        )

        if sign == "-":
            right = -right

        assert a != c

        return Fraction(right - b, a - c)

    if difficulty == 4:
        total_a, coefficient, total_b = require_match(
            r"x \+ y = (\d+); "
            r"(\d+)x \+ y = (\d+)\. "
            r"What is x\?",
            prompt,
        )

        assert coefficient != 1

        return Fraction(
            total_b - total_a,
            coefficient - 1,
        )

    if difficulty == 5:
        a, b, c, d, total = require_match(
            r"Solve for x: (\d+)\(x \+ (\d+)\) "
            r"- (\d+)x \+ (\d+) = (-?\d+)\.",
            prompt,
        )

        assert a != c

        return Fraction(
            total - a * b - d,
            a - c,
        )

    raise AssertionError("Unsupported difficulty.")


SOLVERS = {
    "number_sequences": solve_sequence,
    "quantitative_relationships": solve_relationship,
    "mathematical_logic": solve_logic,
}


def verify_question(question):
    family = question["family"]
    difficulty = question["difficulty"]

    expected = SOLVERS[family](
        question["prompt"],
        difficulty,
    )

    matches = [
        option["id"]
        for option in question["options"]
        if Fraction(option["value"]) == expected
    ]

    assert len(matches) == 1, (
        "Question must have exactly one matching "
        "mathematical answer."
    )

    assert matches[0] == question["correct_option_id"], (
        "Incorrect stored answer key: "
        + question["prompt"]
    )


def run_tests():
    total = 0

    for family in GENERATORS:
        for difficulty in range(1, 6):
            prompts = set()
            contents = set()

            for index in range(2000):
                question = generate_question(
                    family,
                    difficulty,
                    f"independent-verification-{index}",
                )

                verify_question(question)

                prompts.add(question["prompt"])
                contents.add(question["content_hash"])

                total += 1

            print(
                f"{family}, level {difficulty}: "
                f"2000 answers verified; "
                f"{len(prompts)} unique prompts; "
                f"{len(contents)} unique content hashes."
            )

    assert total == 30000

    print()
    print("ALL 30,000 MATHEMATICAL VERIFICATIONS PASSED")

    question = generate_question(
        "mathematical_logic",
        3,
        "negative-control",
    )

    question["correct_option_id"] = next(
        option["id"]
        for option in question["options"]
        if option["id"] != question["correct_option_id"]
    )

    try:
        verify_question(question)
    except AssertionError:
        print("Incorrect answer-key detection: PASSED")
    else:
        raise AssertionError(
            "Verifier failed to detect an incorrect key."
        )

    print()
    print("QUANTITATIVE VERIFICATION COMPLETE")


if __name__ == "__main__":
    run_tests()

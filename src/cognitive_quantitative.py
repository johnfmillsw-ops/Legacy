"""
Legacy Phase VII: Quantitative reasoning generators.

Original procedural items.
Difficulty levels are provisional, not calibrated.
"""

from cognitive_engine import (
    build_question,
    question_rng,
    score_response,
    create_seed,
)

FAMILY_VERSION = 2


def numeric_distractors(answer, candidates, rng):
    values = []

    for candidate in candidates:
        if candidate != answer and candidate not in values:
            values.append(candidate)

    distance = 1

    while len(values) < 4:
        for candidate in (
            answer - distance,
            answer + distance,
        ):
            if candidate != answer and candidate not in values:
                values.append(candidate)

        distance += 1

    rng.shuffle(values)

    return [str(value) for value in values[:4]]


def number_sequences(difficulty, seed):
    family = "number_sequences"

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    start = rng.randint(2, 100)

    if difficulty == 1:
        step = rng.randint(2, 30)

        terms = [
            start + step * i
            for i in range(7)
        ]

        explanation = (
            f"Add {step} to each preceding term."
        )

        candidates = [
            terms[6] - step,
            terms[6] + step,
            terms[5] + step - 1,
            terms[5] + step + 1,
        ]

    elif difficulty == 2:
        ratio = rng.randint(2, 6)
        start = rng.randint(1, 40)

        terms = [
            start * ratio ** i
            for i in range(7)
        ]

        explanation = (
            f"Multiply each preceding term by {ratio}."
        )

        candidates = [
            terms[5] * (ratio - 1),
            terms[5] * (ratio + 1),
            terms[5] + ratio,
            terms[6] + terms[5],
        ]

    elif difficulty == 3:
        step = rng.randint(2, 20)
        growth = rng.randint(2, 12)

        terms = [start]

        for i in range(6):
            terms.append(
                terms[-1] + step + growth * i
            )

        explanation = (
            f"The first difference is {step}; "
            f"each subsequent difference increases by "
            f"{growth}."
        )

        candidates = [
            terms[5] + step,
            terms[6] - growth,
            terms[6] + growth,
            terms[6] + step,
        ]

    elif difficulty == 4:
        multiplier = rng.randint(2, 5)
        addition = rng.randint(3, 30)

        terms = [start]

        for i in range(6):
            if i % 2 == 0:
                terms.append(
                    terms[-1] * multiplier
                )
            else:
                terms.append(
                    terms[-1] + addition
                )

        explanation = (
            f"Alternate multiplying by {multiplier} "
            f"and adding {addition}, starting with "
            "multiplication."
        )

        candidates = [
            terms[5] * multiplier,
            terms[5] - addition,
            terms[5] + multiplier,
            terms[6] + addition,
        ]

    else:
        first = rng.randint(2, 15)
        second = rng.randint(20, 40)

        step_a = rng.randint(2, 7)
        step_b = rng.randint(3, 9)

        terms = []

        for i in range(7):
            if i % 2 == 0:
                terms.append(
                    first + (i // 2) * step_a
                )
            else:
                terms.append(
                    second + (i // 2) * step_b
                )

        explanation = (
            f"Odd-position terms increase by {step_a}; "
            f"even-position terms increase by {step_b}."
        )

        candidates = [
            terms[5] + step_b,
            terms[4] + step_b,
            terms[5] + step_a,
            terms[6] + step_a,
        ]

    answer = terms[-1]

    prompt = (
        "Identify the intended numerical pattern. "
        "Which number comes next? "
        + ", ".join(str(n) for n in terms[:-1])
        + ", ?"
    )

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=prompt,
        correct_answer=str(answer),
        distractors=numeric_distractors(
            answer, candidates, rng
        ),
        explanation=explanation,
        family_version=FAMILY_VERSION,
    )


def quantitative_relationships(difficulty, seed):
    family = "quantitative_relationships"

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    if difficulty == 1:
        price = rng.randint(2, 25)
        quantity = rng.randint(2, 8)
        target = quantity + rng.randint(2, 9)

        answer = price * target

        prompt = (
            f"{quantity} identical items cost "
            f"${price * quantity}. "
            f"At the same unit price, how much do "
            f"{target} items cost in dollars?"
        )

        explanation = (
            f"The unit price is {price}. "
            f"Multiply {price} by {target}."
        )

        candidates = [
            price * quantity,
            price + target,
            answer + price,
            answer - price,
        ]

    elif difficulty == 2:
        workers = rng.randint(2, 25)
        hours = rng.randint(2, 30)
        factor = rng.randint(2, 6)

        answer = hours

        prompt = (
            f"{workers} workers complete a task in "
            f"{hours * factor} hours. "
            f"How many hours would {workers * factor} "
            "workers need, assuming identical constant "
            "rates and no interference?"
        )

        explanation = (
            f"The workforce increases by a factor of "
            f"{factor}, so the required time is divided "
            f"by {factor}."
        )

        candidates = [
            hours * factor,
            hours * factor ** 2,
            hours + factor,
            hours - 1,
        ]

    elif difficulty == 3:
        rate_a = rng.randint(3, 15)
        rate_b = rng.randint(4, 18)
        hours = rng.randint(2, 10)

        answer = (rate_a + rate_b) * hours

        prompt = (
            f"Machine A produces {rate_a} units per hour. "
            f"Machine B produces {rate_b} units per hour. "
            f"How many units do they produce together "
            f"in {hours} hours at constant rates?"
        )

        explanation = (
            "Add the two production rates, then "
            "multiply by the operating time."
        )

        candidates = [
            rate_a * hours,
            rate_b * hours,
            rate_a + rate_b + hours,
            answer + rate_a,
        ]

    elif difficulty == 4:
        original = rng.randint(2, 100) * 400
        increase = rng.choice([5, 10, 15, 20, 25, 30, 40, 50])
        decrease = rng.choice([5, 10, 15, 20, 25, 30, 40, 50])

        intermediate = original * (100 + increase) // 100

        answer = intermediate * (100 - decrease) // 100

        prompt = (
            f"A value of {original} increases by "
            f"{increase}%, then the resulting value "
            f"decreases by {decrease}%. "
            "What is the final value?"
        )

        explanation = (
            f"After the increase: {intermediate}. "
            f"Apply the decrease to that value, "
            "not to the original value."
        )

        candidates = [
            original,
            intermediate,
            original * (100 + increase - decrease) // 100,
            original * (100 - decrease) // 100,
        ]

    else:
        count_a = rng.randint(2, 8)
        count_b = rng.randint(2, 8)

        average = rng.randint(30, 70)
        difference = rng.randint(1, 3)

        value_a = average - count_b * difference
        value_b = average + count_a * difference

        answer = average

        prompt = (
            f"Group A contains {count_a} measurements "
            f"with an average of {value_a}. "
            f"Group B contains {count_b} measurements "
            f"with an average of {value_b}. "
            "What is the average of all measurements "
            "combined?"
        )

        explanation = (
            f"Calculate ({count_a} x {value_a} + "
            f"{count_b} x {value_b}) / "
            f"({count_a} + {count_b})."
        )

        candidates = [
            value_a,
            value_b,
            (value_a + value_b) // 2,
            average + difference,
        ]

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=prompt,
        correct_answer=str(answer),
        distractors=numeric_distractors(
            answer, candidates, rng
        ),
        explanation=explanation,
        family_version=FAMILY_VERSION,
    )


def mathematical_logic(difficulty, seed):
    family = "mathematical_logic"

    rng = question_rng(
        family, difficulty, seed, FAMILY_VERSION
    )

    x = rng.randint(2, 30)
    a = rng.randint(2, 9)
    b = rng.randint(2, 20)

    if difficulty == 1:
        total = x + b

        prompt = (
            f"A number plus {b} equals {total}. "
            "What is the number?"
        )

        explanation = f"Subtract {b} from {total}."

        candidates = [
            total,
            total + b,
            b,
            x + 1,
        ]

    elif difficulty == 2:
        total = a * x + b

        prompt = (
            f"A number multiplied by {a}, then "
            f"increased by {b}, equals {total}. "
            "What is the number?"
        )

        explanation = (
            f"Subtract {b} from {total}, "
            f"then divide by {a}."
        )

        candidates = [
            total - b,
            total // a,
            x + a,
            x - 1,
        ]

    elif difficulty == 3:
        c = a + rng.randint(1, 6)
        right = (a - c) * x + b

        prompt = (
            f"Solve for x: {a}x + {b} "
            f"= {c}x "
            + (
                f"+ {right}"
                if right >= 0
                else f"- {abs(right)}"
            )
        )

        explanation = (
            f"Rearrange to obtain "
            f"{c - a}x = {b - right}."
        )

        candidates = [
            -x,
            x + c - a,
            x - 1,
            x + 1,
        ]

    elif difficulty == 4:
        y = rng.randint(2, 25)

        total_a = x + y
        total_b = a * x + y

        prompt = (
            f"x + y = {total_a}; "
            f"{a}x + y = {total_b}. "
            "What is x?"
        )

        explanation = (
            "Subtract the first equation from the "
            f"second: {a - 1}x = "
            f"{total_b - total_a}."
        )

        candidates = [
            y,
            total_a,
            total_b - total_a,
            x + 1,
        ]

    else:
        c = rng.randint(2, 7)
        d = a * rng.randint(1, 4)

        total = a * (x + b) - c * x + d

        while a == c:
            c = rng.randint(2, 7)

        total = a * (x + b) - c * x + d

        prompt = (
            f"Solve for x: {a}(x + {b}) "
            f"- {c}x + {d} = {total}."
        )

        explanation = (
            "Expand the parentheses and combine "
            f"like terms: {a - c}x = "
            f"{total - a * b - d}."
        )

        candidates = [
            x + b,
            x - b,
            -x,
            x + a,
        ]

    return build_question(
        family=family,
        difficulty=difficulty,
        seed=seed,
        prompt=prompt,
        correct_answer=str(x),
        distractors=numeric_distractors(
            x, candidates, rng
        ),
        explanation=explanation,
        family_version=FAMILY_VERSION,
    )


GENERATORS = {
    "number_sequences": number_sequences,
    "quantitative_relationships": quantitative_relationships,
    "mathematical_logic": mathematical_logic,
}


def generate_question(family, difficulty, seed=None):
    if family not in GENERATORS:
        raise ValueError("Unknown quantitative family.")

    if seed is None:
        seed = create_seed()

    return GENERATORS[family](difficulty, seed)


def run_self_tests():
    total = 0

    for family in GENERATORS:
        for difficulty in range(1, 6):
            hashes = set()
            positions = set()

            for index in range(1000):
                seed = f"test-{index}"

                question = generate_question(
                    family, difficulty, seed
                )

                assert question == generate_question(
                    family, difficulty, seed
                )

                assert len(question["options"]) == 5

                values = [
                    int(option["value"])
                    for option in question["options"]
                ]

                assert len(set(values)) == 5

                correct_id = question["correct_option_id"]

                for option in question["options"]:
                    result = score_response(
                        question, option["id"]
                    )

                    assert result["raw_points"] == int(
                        option["id"] == correct_id
                    )

                hashes.add(question["content_hash"])
                positions.add(correct_id)

                total += 1

            assert len(hashes) > 20
            assert positions == set("ABCDE")

            print(
                f"{family}, level {difficulty}: "
                f"1000 generated, "
                f"{len(hashes)} unique content hashes, "
                "PASSED"
            )

    assert total == 15000

    print()
    print("ALL 15,000 GENERATION TESTS PASSED")
    print()
    print("Sample questions:")

    for family in GENERATORS:
        question = generate_question(family, 5)

        print()
        print(question["prompt"])

        for option in question["options"]:
            print(option["id"], option["value"])

        print(
            "Answer:",
            question["correct_option_id"]
        )

        print(question["explanation"])


if __name__ == "__main__":
    run_self_tests()

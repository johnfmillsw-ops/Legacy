
"""
Legacy Phase VII: Scoring sensitivity diagnostics.

Examines theoretical scoring behavior without
claiming empirical calibration or population norms.
"""

from math import fsum, isclose
from statistics import mean

from cognitive_psychometrics import (
    ItemParameters,
    estimate_eap,
)

from cognitive_scoring_parameters import (
    parameters_for_item,
)

from cognitive_domain_scoring import (
    UNTIMED_DOMAINS,
)

from cognitive_composite_scoring import (
    ability_to_scale,
)

from cognitive_research_bank import (
    build_research_bank,
)

from cognitive_blueprint import (
    assemble_assessment,
)


DIAGNOSTICS_VERSION = 1


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def estimate_score(parameters, responses):

    estimate = estimate_eap(
        parameters,
        responses,
    )

    return ability_to_scale(
        estimate["theta"]
    )


def domain_parameters(form, domain):

    records = [
        record
        for section in form["sections"]
        if section["domain"] == domain
        for block in section["blocks"]
        for record in block["items"]
    ]

    require(
        len(records) == 12,
        "Incorrect domain item count.",
    )

    return [
        parameters_for_item(record)
        for record in records
    ]


def score_range(parameters):

    count = len(parameters)

    return {
        "minimum": estimate_score(
            parameters, [0] * count
        ),
        "maximum": estimate_score(
            parameters, [1] * count
        ),
    }


def response_progression(parameters):

    ordered = sorted(
        parameters,
        key=lambda item: item.difficulty,
    )

    count = len(ordered)

    results = []

    for correct in range(count + 1):

        easier_first = (
            [1] * correct
            + [0] * (count - correct)
        )

        harder_first = (
            [0] * (count - correct)
            + [1] * correct
        )

        results.append({
            "correct": correct,
            "easier_first": estimate_score(
                ordered,
                easier_first,
            ),
            "harder_first": estimate_score(
                ordered,
                harder_first,
            ),
        })

    return results


def adjusted_parameters(
    parameters,
    difficulty_multiplier=1.0,
    difficulty_shift=0.0,
    discrimination=1.0,
    guessing_multiplier=1.0,
):

    return [
        ItemParameters(
            difficulty=(
                item.difficulty
                * difficulty_multiplier
                + difficulty_shift
            ),
            discrimination=discrimination,
            lower_asymptote=(
                item.lower_asymptote
                * guessing_multiplier
            ),
            model="3PL",
        )
        for item in parameters
    ]


def sensitivity_analysis(parameters):

    ordered = sorted(
        parameters,
        key=lambda item: item.difficulty,
    )

    patterns = {
        "all_incorrect": [0] * 12,
        "six_correct": [1] * 6 + [0] * 6,
        "nine_correct": [1] * 9 + [0] * 3,
        "all_correct": [1] * 12,
    }

    scenarios = {
        "baseline": {},
        "compressed_difficulty": {
            "difficulty_multiplier": 0.5,
        },
        "expanded_difficulty": {
            "difficulty_multiplier": 1.5,
        },
        "easier_items": {
            "difficulty_shift": -0.5,
        },
        "harder_items": {
            "difficulty_shift": 0.5,
        },
        "lower_discrimination": {
            "discrimination": 0.75,
        },
        "higher_discrimination": {
            "discrimination": 1.5,
        },
        "reduced_guessing": {
            "guessing_multiplier": 0.5,
        },
        "no_guessing": {
            "guessing_multiplier": 0.0,
        },
    }

    results = {}

    for name, settings in scenarios.items():

        adjusted = adjusted_parameters(
            ordered,
            **settings,
        )

        results[name] = {
            pattern: estimate_score(
                adjusted,
                responses,
            )
            for pattern, responses
            in patterns.items()
        }

    return results


def run_tests():

    bank = build_research_bank()

    form = assemble_assessment(
        bank,
        "scoring-diagnostics-v1",
    )

    ranges = {}

    print("DOMAIN SCORE RANGES")
    print()

    for domain in UNTIMED_DOMAINS:

        parameters = domain_parameters(
            form, domain
        )

        bounds = score_range(parameters)

        require(
            bounds["minimum"] < bounds["maximum"],
            "Invalid theoretical score range.",
        )

        ranges[domain] = bounds

        print(
            f"{domain:25s}"
            f"{bounds['minimum']:8.2f}"
            f"{bounds['maximum']:8.2f}"
        )

    minimum = mean(
        bounds["minimum"]
        for bounds in ranges.values()
    )

    maximum = mean(
        bounds["maximum"]
        for bounds in ranges.values()
    )

    print()
    print(f"Composite minimum: {minimum:.2f}")
    print(f"Composite maximum: {maximum:.2f}")
    print()
    print("Theoretical score bounds: PASSED")

    parameters = domain_parameters(
        form,
        "fluid_reasoning",
    )

    progression = response_progression(
        parameters
    )

    print()
    print("RESPONSE PROGRESSION")
    print()
    print("Correct    Easier first    Harder first")

    for row in progression:

        print(
            f"{row['correct']:>7}/12"
            f"{row['easier_first']:>15.2f}"
            f"{row['harder_first']:>16.2f}"
        )

    for key in (
        "easier_first",
        "harder_first",
    ):

        values = [
            row[key]
            for row in progression
        ]

        require(
            all(
                a < b
                for a, b in zip(
                    values,
                    values[1:],
                )
            ),
            "Response monotonicity failed.",
        )

    print()
    print("Response monotonicity: PASSED")

    require(
        isclose(
            progression[0]["easier_first"],
            progression[0]["harder_first"],
            abs_tol=1e-9,
        )
        and isclose(
            progression[-1]["easier_first"],
            progression[-1]["harder_first"],
            abs_tol=1e-9,
        ),
        "Inconsistent endpoint scoring.",
    )

    print("Score endpoint consistency: PASSED")

    differences = [
        row["harder_first"] - row["easier_first"]
        for row in progression[1:-1]
    ]

    print()
    print(
        "Harder-first score differences:",
        [round(value, 3) for value in differences],
    )

    if all(value > 0 for value in differences):

        print(
            "Harder-first scoring advantage observed."
        )

    else:

        print(
            "WARNING: Difficulty advantage is "
            "not consistent under the current "
            "response model."
        )

    sensitivity = sensitivity_analysis(
        parameters
    )

    print()
    print("PARAMETER SENSITIVITY")
    print()
    print(
        "Scenario"
        "                      0/12"
        "     6/12"
        "     9/12"
        "    12/12"
    )

    for name, values in sensitivity.items():

        print(
            f"{name:27s}"
            f"{values['all_incorrect']:9.2f}"
            f"{values['six_correct']:9.2f}"
            f"{values['nine_correct']:9.2f}"
            f"{values['all_correct']:9.2f}"
        )

    print()
    print("Nine parameter scenarios evaluated: PASSED")

    print()
    print("PARAMETER SENSITIVITY RANGES")

    for pattern in (
        "all_incorrect",
        "six_correct",
        "nine_correct",
        "all_correct",
    ):

        scores = [
            result[pattern]
            for result in sensitivity.values()
        ]

        print(
            f"{pattern:18s}"
            f"{min(scores):8.2f}"
            f"{max(scores):8.2f}"
            f"  spread={max(scores)-min(scores):.2f}"
        )

    print()
    print("ALTERNATE FORM SCORE BOUNDS")

    form_bounds = []

    for index in range(10):

        alternate = assemble_assessment(
            bank,
            f"diagnostic-form-{index}",
        )

        bounds = [
            score_range(
                domain_parameters(
                    alternate,
                    domain,
                )
            )
            for domain in UNTIMED_DOMAINS
        ]

        low = mean(
            item["minimum"]
            for item in bounds
        )

        high = mean(
            item["maximum"]
            for item in bounds
        )

        form_bounds.append((low, high))

        print(
            f"Form {index + 1:02d}: "
            f"{low:.2f} to {high:.2f}"
        )

    print()
    print(
        "Minimum-score spread:",
        round(
            max(x[0] for x in form_bounds)
            - min(x[0] for x in form_bounds),
            4,
        ),
    )

    print(
        "Maximum-score spread:",
        round(
            max(x[1] for x in form_bounds)
            - min(x[1] for x in form_bounds),
            4,
        ),
    )

    print()
    print("Ten alternate forms evaluated: PASSED")

    print()
    print("DIAGNOSTIC LIMITATIONS")
    print("Human calibration: unavailable")
    print("Population norms: unavailable")
    print("Empirical score equivalence: unverified")
    print("Clinical IQ interpretation: unsupported")
    print()
    print("ALL SCORING DIAGNOSTICS COMPLETED")


if __name__ == "__main__":
    run_tests()

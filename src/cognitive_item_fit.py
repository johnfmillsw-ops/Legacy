
"""
Legacy Phase VII: Exploratory item-fit diagnostics.

Leave-one-item-out posterior predictions,
corrected item-total correlations and
pairwise posterior residual correlations.

Research only. Diagnostic flags require
empirical evaluation and professional review.
"""

import math
from collections import Counter

from cognitive_calibration import (
    calibrate_rasch,
    validate_dataset,
    quadrature_grid,
)

from cognitive_psychometrics import (
    logistic,
    softplus,
)

ITEM_FIT_VERSION = 1

MIN_PAIR_OBSERVATIONS = 50

# Provisional screening thresholds.
# Not validated item rejection criteria.
LOW_CORRELATION_THRESHOLD = 0.15
RESIDUAL_CORRELATION_THRESHOLD = 0.20


def pearson(left, right):
    left = tuple(left)
    right = tuple(right)

    if len(left) != len(right):
        raise ValueError(
            "Correlation input lengths differ."
        )

    if len(left) < 2:
        return None

    mean_left = math.fsum(left) / len(left)
    mean_right = math.fsum(right) / len(right)

    centered_left = [
        value - mean_left
        for value in left
    ]

    centered_right = [
        value - mean_right
        for value in right
    ]

    variance_left = math.fsum(
        value ** 2
        for value in centered_left
    )

    variance_right = math.fsum(
        value ** 2
        for value in centered_right
    )

    if variance_left <= 0 or variance_right <= 0:
        return None

    covariance = math.fsum(
        a * b
        for a, b in zip(
            centered_left,
            centered_right,
        )
    )

    result = covariance / math.sqrt(
        variance_left * variance_right
    )

    return max(-1.0, min(1.0, result))


def posterior_weights(
    response,
    difficulties,
    grid,
    log_prior,
    excluded=(),
):
    excluded = set(excluded)

    log_weights = list(log_prior)

    for index, value in enumerate(response):
        if value is None or index in excluded:
            continue

        difficulty = difficulties[index]

        for k, theta in enumerate(grid):
            if value == 1:
                log_weights[k] -= softplus(
                    difficulty - theta
                )
            else:
                log_weights[k] -= softplus(
                    theta - difficulty
                )

    maximum = max(log_weights)

    weights = [
        math.exp(value - maximum)
        for value in log_weights
    ]

    total = math.fsum(weights)

    return [
        weight / total
        for weight in weights
    ]


def predict_response(
    response,
    item_index,
    difficulties,
    grid,
    log_prior,
):
    weights = posterior_weights(
        response,
        difficulties,
        grid,
        log_prior,
        excluded=(item_index,),
    )

    difficulty = difficulties[item_index]

    return math.fsum(
        weight * logistic(theta - difficulty)
        for theta, weight in zip(
            grid, weights
        )
    )


def corrected_item_total(
    responses,
    item_index,
):
    item_values = []
    rest_scores = []

    # Complete cases only, so rest scores
    # refer to identical item sets.
    for row in responses:
        if any(value is None for value in row):
            continue

        item_values.append(row[item_index])

        rest_scores.append(
            sum(
                value
                for index, value in enumerate(row)
                if index != item_index
            )
        )

    count = len(item_values)

    if count < MIN_PAIR_OBSERVATIONS:
        return None, count

    return pearson(
        item_values,
        rest_scores,
    ), count


def analyze_item_fit(
    item_ids,
    responses,
    *,
    grid_points=81,
):
    item_ids, responses, statistics = (
        validate_dataset(
            item_ids, responses
        )
    )

    if len(item_ids) < 3:
        raise ValueError(
            "At least three items required "
            "for these diagnostics."
        )

    if len(item_ids) > 30:
        raise ValueError(
            "Current diagnostic limit is 30 items."
        )

    calibration = calibrate_rasch(
        item_ids,
        responses,
        grid_points=grid_points,
    )

    if not calibration["converged"]:
        raise ArithmeticError(
            "Calibration did not converge."
        )

    if any(
        item["quality_flags"]
        for item in calibration["items"]
    ):
        raise ArithmeticError(
            "Unresolved calibration quality flags."
        )

    difficulties = [
        item["difficulty"]
        for item in calibration["items"]
    ]

    grid, log_prior = quadrature_grid(
        grid_points
    )

    patterns = Counter(responses)

    prediction_cache = {}
    residual_cache = {}

    for pattern in patterns:
        predictions = []
        residuals = []

        for index, value in enumerate(pattern):
            if value is None:
                predictions.append(None)
                residuals.append(None)
                continue

            prediction = predict_response(
                pattern,
                index,
                difficulties,
                grid,
                log_prior,
            )

            predictions.append(prediction)
            residuals.append(value - prediction)

        prediction_cache[pattern] = predictions
        residual_cache[pattern] = residuals

    item_results = []

    for index, item_id in enumerate(item_ids):
        observed = []
        predicted = []

        for pattern, frequency in patterns.items():
            if pattern[index] is None:
                continue

            observed.extend(
                [pattern[index]] * frequency
            )

            predicted.extend(
                [prediction_cache[pattern][index]]
                * frequency
            )

        count = len(observed)

        observed_rate = math.fsum(
            observed
        ) / count

        predicted_rate = math.fsum(
            predicted
        ) / count

        brier_score = math.fsum(
            (actual - expected) ** 2
            for actual, expected in zip(
                observed, predicted
            )
        ) / count

        correlation, complete_cases = (
            corrected_item_total(
                responses, index
            )
        )

        flags = []

        if correlation is None:
            flags.append(
                "item_total_correlation_unavailable"
            )

        elif correlation < 0:
            flags.append(
                "negative_item_total_correlation"
            )

        elif correlation < LOW_CORRELATION_THRESHOLD:
            flags.append(
                "low_item_total_correlation"
            )

        item_results.append({
            "item_id": item_id,
            "observed_count": count,
            "observed_accuracy": observed_rate,
            "predicted_accuracy": predicted_rate,
            "mean_prediction_residual":
                observed_rate - predicted_rate,
            "brier_score": brier_score,
            "corrected_item_total_correlation":
                correlation,
            "complete_case_count": complete_cases,
            "quality_flags": flags,
        })

    pair_results = []

    for first in range(len(item_ids)):
        for second in range(
            first + 1, len(item_ids)
        ):
            left = []
            right = []

            for pattern, frequency in patterns.items():
                if (
                    pattern[first] is None
                    or pattern[second] is None
                ):
                    continue

                # Exclude both items when
                # predicting their responses.
                weights = posterior_weights(
                    pattern,
                    difficulties,
                    grid,
                    log_prior,
                    excluded=(first, second),
                )

                predicted_first = math.fsum(
                    weight * logistic(
                        theta - difficulties[first]
                    )
                    for theta, weight in zip(
                        grid, weights
                    )
                )

                predicted_second = math.fsum(
                    weight * logistic(
                        theta - difficulties[second]
                    )
                    for theta, weight in zip(
                        grid, weights
                    )
                )

                left.extend([
                    pattern[first] - predicted_first
                ] * frequency)

                right.extend([
                    pattern[second] - predicted_second
                ] * frequency)

            count = len(left)

            correlation = (
                pearson(left, right)
                if count >= MIN_PAIR_OBSERVATIONS
                else None
            )

            flags = []

            if correlation is None:
                flags.append(
                    "residual_correlation_unavailable"
                )

            elif correlation >= (
                RESIDUAL_CORRELATION_THRESHOLD
            ):
                flags.append(
                    "positive_residual_association"
                )

            pair_results.append({
                "first_item": item_ids[first],
                "second_item": item_ids[second],
                "paired_observations": count,
                "residual_correlation": correlation,
                "quality_flags": flags,
            })

    return {
        "item_fit_version": ITEM_FIT_VERSION,
        "model": "1PL",
        "participant_count": len(responses),
        "item_count": len(item_ids),
        "items": item_results,
        "item_pairs": pair_results,
        "thresholds_calibrated": False,
        "independent_validation": False,
        "research_only": True,
        "scientific_approval_granted": False,
        "iq_reporting_enabled": False,
    }


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_tests():
    from random import Random

    require(
        math.isclose(
            pearson([1, 2, 3], [2, 4, 6]),
            1.0,
        ),
        "Positive correlation failed.",
    )

    require(
        math.isclose(
            pearson([1, 2, 3], [6, 4, 2]),
            -1.0,
        ),
        "Negative correlation failed.",
    )

    require(
        pearson([1, 1, 1], [1, 2, 3])
        is None,
        "Constant correlation should be undefined.",
    )

    print("Analytical correlation tests: PASSED")

    grid, log_prior = quadrature_grid(81)

    first = predict_response(
        [1, 0, 1],
        0,
        [0, 0, 0],
        grid,
        log_prior,
    )

    second = predict_response(
        [0, 0, 1],
        0,
        [0, 0, 0],
        grid,
        log_prior,
    )

    require(
        math.isclose(first, second),
        "Target response leaked into prediction.",
    )

    print("Target-response exclusion: PASSED")

    rng = Random(20261128)

    difficulties = [
        -1.5, -1.0, -0.5,
        0.0, 0.5, 1.0,
    ]

    item_ids = [
        f"synthetic_{i}"
        for i in range(len(difficulties))
    ]

    responses = []

    for _ in range(2500):
        theta = rng.gauss(0, 1)

        responses.append([
            int(
                rng.random()
                < logistic(theta - difficulty)
            )
            for difficulty in difficulties
        ])

    clean = analyze_item_fit(
        item_ids, responses
    )

    require(
        len(clean["items"]) == 6,
        "Incorrect item count.",
    )

    require(
        len(clean["item_pairs"]) == 15,
        "Incorrect pair count.",
    )

    print("Diagnostic coverage: PASSED")

    print()
    print("Synthetic item diagnostics:")

    for item in clean["items"]:
        correlation = item[
            "corrected_item_total_correlation"
        ]

        require(
            correlation is not None
            and correlation > 0,
            "Expected positive item association.",
        )

        require(
            0 <= item["brier_score"] <= 1,
            "Invalid prediction error.",
        )

        print(
            f"  {item['item_id']} | "
            f"Item-total r: {correlation:.3f} | "
            f"Brier: {item['brier_score']:.3f}"
        )

    print("Synthetic item behavior: PASSED")

    # Introduce an exact duplicate item
    # to create strong local dependence.
    dependent = [
        list(row) + [row[2]]
        for row in responses
    ]

    duplicated = analyze_item_fit(
        item_ids + ["duplicate_item"],
        dependent,
    )

    pair = next(
        pair
        for pair in duplicated["item_pairs"]
        if pair["first_item"] == "synthetic_2"
        and pair["second_item"] == "duplicate_item"
    )

    require(
        pair["residual_correlation"] > 0.99,
        "Duplicate item dependence not detected.",
    )

    require(
        "positive_residual_association"
        in pair["quality_flags"],
        "Dependent item pair not flagged.",
    )

    print("Duplicate item dependence detection: PASSED")

    # Introduce an item negatively related
    # to the intended ability construct.
    reversed_responses = [
        list(row) + [1 - row[2]]
        for row in responses
    ]

    reversed_result = analyze_item_fit(
        item_ids + ["reversed_item"],
        reversed_responses,
    )

    reversed_item = reversed_result["items"][-1]

    require(
        reversed_item[
            "corrected_item_total_correlation"
        ] < 0,
        "Negative item association not detected.",
    )

    require(
        "negative_item_total_correlation"
        in reversed_item["quality_flags"],
        "Negative item association not flagged.",
    )

    print("Negative item association detection: PASSED")

    incomplete = [
        [
            None if rng.random() < 0.1
            else value
            for value in row
        ]
        for row in responses
    ]

    incomplete = [
        row for row in incomplete
        if any(value is not None for value in row)
    ]

    missing_result = analyze_item_fit(
        item_ids, incomplete
    )

    require(
        all(
            item["observed_count"]
            <= len(incomplete)
            for item in missing_result["items"]
        ),
        "Missing response counts invalid.",
    )

    print("Incomplete response diagnostics: PASSED")

    require(
        clean["research_only"]
        and not clean["iq_reporting_enabled"]
        and not clean["scientific_approval_granted"]
        and not clean["thresholds_calibrated"],
        "Scientific reporting safeguards failed.",
    )

    print("Scientific reporting safeguards: PASSED")

    print()
    print("ALL ITEM FIT DIAGNOSTICS TESTS PASSED")


if __name__ == "__main__":
    run_tests()

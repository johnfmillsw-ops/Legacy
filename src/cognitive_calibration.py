
"""
Legacy Phase VII: Research-only item calibration.

Marginal maximum likelihood Rasch calibration
using expectation-maximization and numerical
integration over a standard normal ability prior.

Supports incomplete response matrices.
Does not authorize validated cognitive reporting.
"""

import math
from collections import Counter

from cognitive_psychometrics import (
    logistic,
    softplus,
    ItemParameters,
    item_information,
)

CALIBRATION_VERSION = 1

# Engineering safeguards, not validated sample
# size recommendations.
MIN_PARTICIPANTS = 100
MIN_ITEM_RESPONSES = 50
MIN_OUTCOME_COUNT = 5

DIFFICULTY_BOUND = 8.0


def validate_dataset(item_ids, responses):
    item_ids = tuple(item_ids)
    responses = tuple(
        tuple(row) for row in responses
    )

    if len(item_ids) < 2:
        raise ValueError(
            "At least two items are required."
        )

    if any(
        not isinstance(item, str)
        or not item.strip()
        for item in item_ids
    ):
        raise ValueError("Invalid item identity.")

    if len(set(item_ids)) != len(item_ids):
        raise ValueError("Duplicate item identity.")

    if len(responses) < MIN_PARTICIPANTS:
        raise ValueError(
            "Insufficient participant records."
        )

    for row in responses:
        if len(row) != len(item_ids):
            raise ValueError(
                "Response matrix width mismatch."
            )

        for value in row:
            if value is not None and (
                type(value) is not int
                or value not in (0, 1)
            ):
                raise ValueError(
                    "Responses must be 0, 1 or None."
                )

        if all(value is None for value in row):
            raise ValueError(
                "Empty participant response record."
            )

    statistics = []

    for index, item_id in enumerate(item_ids):
        counts = Counter(
            row[index]
            for row in responses
            if row[index] is not None
        )

        total = counts[0] + counts[1]

        if total < MIN_ITEM_RESPONSES:
            raise ValueError(
                f"Insufficient responses: {item_id}"
            )

        if min(counts[0], counts[1]) < (
            MIN_OUTCOME_COUNT
        ):
            raise ValueError(
                f"Insufficient outcome variation: "
                f"{item_id}"
            )

        statistics.append({
            "item_id": item_id,
            "observed": total,
            "correct": counts[1],
            "incorrect": counts[0],
            "missing": len(responses) - total,
            "observed_accuracy": counts[1] / total,
        })

    # Require a connected item co-observation
    # graph to avoid disconnected item pools.
    adjacency = [
        set() for _ in item_ids
    ]

    for row in responses:
        observed = [
            index
            for index, value in enumerate(row)
            if value is not None
        ]

        for index in observed:
            adjacency[index].update(observed)

    visited = {0}
    pending = [0]

    while pending:
        current = pending.pop()

        for neighbor in adjacency[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)

    if len(visited) != len(item_ids):
        raise ValueError(
            "Disconnected item response design."
        )

    return item_ids, responses, statistics


def quadrature_grid(points):
    if (
        type(points) is not int
        or not 41 <= points <= 401
        or points % 2 == 0
    ):
        raise ValueError(
            "Use an odd grid size from 41 to 401."
        )

    step = 12.0 / (points - 1)

    grid = [
        -6.0 + index * step
        for index in range(points)
    ]

    weights = [
        math.exp(-0.5 * theta ** 2)
        for theta in grid
    ]

    weights[0] *= 0.5
    weights[-1] *= 0.5

    total = math.fsum(weights)

    log_weights = [
        math.log(weight / total)
        for weight in weights
    ]

    return grid, log_weights


def expectation_step(
    patterns,
    difficulties,
    grid,
    log_prior,
):
    item_count = len(difficulties)
    grid_count = len(grid)

    expected_observed = [
        [0.0] * grid_count
        for _ in difficulties
    ]

    expected_correct = [
        [0.0] * grid_count
        for _ in difficulties
    ]

    log_p = [
        [
            -softplus(b - theta)
            for theta in grid
        ]
        for b in difficulties
    ]

    log_q = [
        [
            -softplus(theta - b)
            for theta in grid
        ]
        for b in difficulties
    ]

    likelihood_terms = []

    for pattern, frequency in patterns.items():
        observed = [
            (index, response)
            for index, response in enumerate(pattern)
            if response is not None
        ]

        log_posterior = list(log_prior)

        for index, response in observed:
            values = (
                log_p[index]
                if response == 1
                else log_q[index]
            )

            for k in range(grid_count):
                log_posterior[k] += values[k]

        maximum = max(log_posterior)

        weights = [
            math.exp(value - maximum)
            for value in log_posterior
        ]

        denominator = math.fsum(weights)

        log_marginal = (
            maximum + math.log(denominator)
        )

        likelihood_terms.append(
            frequency * log_marginal
        )

        posterior = [
            frequency * weight / denominator
            for weight in weights
        ]

        for index, response in observed:
            for k, weight in enumerate(posterior):
                expected_observed[index][k] += weight

                if response == 1:
                    expected_correct[index][k] += weight

    return (
        math.fsum(likelihood_terms),
        expected_observed,
        expected_correct,
    )


def maximize_item(
    grid,
    expected_observed,
    expected_correct,
):
    observed_correct = math.fsum(
        expected_correct
    )

    def residual(difficulty):
        predicted = math.fsum(
            count * logistic(theta - difficulty)
            for theta, count in zip(
                grid, expected_observed
            )
        )

        return predicted - observed_correct

    lower = -DIFFICULTY_BOUND
    upper = DIFFICULTY_BOUND

    if residual(lower) < 0:
        return lower

    if residual(upper) > 0:
        return upper

    for _ in range(60):
        middle = (lower + upper) / 2

        if residual(middle) > 0:
            lower = middle
        else:
            upper = middle

    return (lower + upper) / 2


def calibrate_rasch(
    item_ids,
    responses,
    *,
    grid_points=81,
    max_iterations=300,
    tolerance=0.00001,
):
    if (
        type(max_iterations) is not int
        or not 1 <= max_iterations <= 5000
    ):
        raise ValueError(
            "Invalid iteration limit."
        )

    if (
        type(tolerance) not in (int, float)
        or not math.isfinite(tolerance)
        or not 0 < tolerance <= 0.001
    ):
        raise ValueError(
            "Invalid convergence tolerance."
        )

    item_ids, responses, statistics = (
        validate_dataset(item_ids, responses)
    )

    grid, log_prior = quadrature_grid(
        grid_points
    )

    patterns = Counter(responses)

    difficulties = [
        math.log(
            item["incorrect"] / item["correct"]
        )
        for item in statistics
    ]

    likelihood_history = []
    converged = False

    for iteration in range(1, max_iterations + 1):
        likelihood, observed, correct = (
            expectation_step(
                patterns,
                difficulties,
                grid,
                log_prior,
            )
        )

        if likelihood_history and (
            likelihood
            < likelihood_history[-1] - 0.000001
        ):
            raise ArithmeticError(
                "Marginal likelihood decreased."
            )

        likelihood_history.append(likelihood)

        updated = [
            maximize_item(
                grid,
                observed[index],
                correct[index],
            )
            for index in range(len(item_ids))
        ]

        change = max(
            abs(new - old)
            for new, old in zip(
                updated, difficulties
            )
        )

        difficulties = updated

        if change <= tolerance:
            converged = True
            break

    final_likelihood, _, _ = expectation_step(
        patterns,
        difficulties,
        grid,
        log_prior,
    )

    if final_likelihood < (
        likelihood_history[-1] - 0.000001
    ):
        raise ArithmeticError(
            "Final marginal likelihood decreased."
        )

    likelihood_history.append(final_likelihood)

    items = []

    for statistics_row, difficulty in zip(
        statistics, difficulties
    ):
        parameters = ItemParameters(
            difficulty=difficulty,
            model="1PL",
        )

        flags = []

        if abs(difficulty) >= (
            DIFFICULTY_BOUND - tolerance
        ):
            flags.append("parameter_at_boundary")

        if not converged:
            flags.append("nonconvergence")

        items.append({
            **statistics_row,
            "model": "1PL",
            "difficulty": difficulty,
            "discrimination": 1.0,
            "lower_asymptote": 0.0,
            "information_at_theta_zero":
                item_information(0, parameters),
            "parameter_standard_error": None,
            "quality_flags": flags,
            "qualification_status": "experimental",
        })

    return {
        "calibration_version": CALIBRATION_VERSION,
        "method": "marginal_maximum_likelihood_em",
        "model": "1PL",
        "participant_count": len(responses),
        "item_count": len(item_ids),
        "unique_response_patterns": len(patterns),
        "latent_prior_mean": 0.0,
        "latent_prior_sd": 1.0,
        "grid_points": grid_points,
        "iterations": iteration,
        "converged": converged,
        "log_likelihood": final_likelihood,
        "likelihood_history": likelihood_history,
        "items": items,
        "research_only": True,
        "scientific_approval_granted": False,
        "iq_reporting_enabled": False,
    }


def run_tests():
    from random import Random

    rng = Random(20261128)

    true_difficulties = (
        -2.0, -1.0, 0.0, 1.0, 2.0
    )

    item_ids = [
        f"synthetic_{index}"
        for index in range(
            len(true_difficulties)
        )
    ]

    responses = []

    for _ in range(3000):
        theta = rng.gauss(0, 1)

        responses.append([
            int(
                rng.random()
                < logistic(theta - difficulty)
            )
            for difficulty in true_difficulties
        ])

    result = calibrate_rasch(
        item_ids, responses
    )

    assert result["converged"]

    print("Marginal likelihood convergence: PASSED")

    history = result["likelihood_history"]

    assert all(
        current >= previous - 0.000001
        for previous, current in zip(
            history, history[1:]
        )
    )

    print("Likelihood monotonicity: PASSED")

    print()
    print("Synthetic parameter recovery:")

    errors = []

    for true, item in zip(
        true_difficulties, result["items"]
    ):
        estimated = item["difficulty"]
        error = abs(estimated - true)

        errors.append(error)

        print(
            f"  True: {true:+.3f} | "
            f"Estimated: {estimated:+.3f} | "
            f"Error: {error:.3f}"
        )

    assert max(errors) < 0.25

    rmse = math.sqrt(
        math.fsum(
            error ** 2 for error in errors
        ) / len(errors)
    )

    print(f"  RMSE: {rmse:.4f}")
    print("Synthetic parameter recovery: PASSED")

    estimated = [
        item["difficulty"]
        for item in result["items"]
    ]

    assert estimated == sorted(estimated)

    print("Difficulty ordering: PASSED")

    incomplete = [
        [
            None if rng.random() < 0.15
            else value
            for value in row
        ]
        for row in responses
    ]

    incomplete = [
        row for row in incomplete
        if any(
            value is not None
            for value in row
        )
    ]

    missing_result = calibrate_rasch(
        item_ids, incomplete
    )

    assert missing_result["converged"]

    for true, item in zip(
        true_difficulties,
        missing_result["items"],
    ):
        assert abs(
            item["difficulty"] - true
        ) < 0.35

    print("Incomplete response calibration: PASSED")

    refined = calibrate_rasch(
        item_ids,
        responses,
        grid_points=161,
    )

    for first, second in zip(
        result["items"],
        refined["items"],
    ):
        assert abs(
            first["difficulty"]
            - second["difficulty"]
        ) < 0.0001

    print("Integration resolution stability: PASSED")

    reversed_result = calibrate_rasch(
        item_ids,
        list(reversed(responses)),
    )

    for first, second in zip(
        result["items"],
        reversed_result["items"],
    ):
        assert abs(
            first["difficulty"]
            - second["difficulty"]
        ) < 0.000001

    print("Participant order invariance: PASSED")

    limited = calibrate_rasch(
        item_ids,
        responses,
        max_iterations=1,
    )

    assert not limited["converged"]

    assert all(
        "nonconvergence" in item["quality_flags"]
        for item in limited["items"]
    )

    print("Nonconvergence detection: PASSED")

    invalid_cases = (
        lambda: calibrate_rasch(
            item_ids, responses[:10]
        ),
        lambda: calibrate_rasch(
            ["duplicate"] * 5, responses
        ),
        lambda: calibrate_rasch(
            item_ids, [[1] * 5] * 100
        ),
        lambda: calibrate_rasch(
            item_ids, [[True] * 5] * 100
        ),
        lambda: calibrate_rasch(
            item_ids, [[None] * 5] * 100
        ),
        lambda: calibrate_rasch(
            item_ids, [[0, 1]] * 100
        ),
        lambda: calibrate_rasch(
            item_ids, responses,
            grid_points=80,
        ),
        lambda: calibrate_rasch(
            item_ids, responses,
            tolerance=0,
        ),
        lambda: calibrate_rasch(
            ["a", "b", "c", "d"],
            [
                [i % 2, (i + 1) % 2, None, None]
                for i in range(100)
            ] + [
                [None, None, i % 2, (i + 1) % 2]
                for i in range(100)
            ],
        ),
    )

    for operation in invalid_cases:
        try:
            operation()
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Invalid calibration input accepted."
            )

    print("9 invalid-input controls: PASSED")

    assert result["research_only"]
    assert not result["iq_reporting_enabled"]
    assert not result["scientific_approval_granted"]

    assert all(
        item["qualification_status"]
        == "experimental"
        for item in result["items"]
    )

    print("Scientific reporting safeguards: PASSED")

    print()
    print("ALL EMPIRICAL CALIBRATION TESTS PASSED")


if __name__ == "__main__":
    run_tests()

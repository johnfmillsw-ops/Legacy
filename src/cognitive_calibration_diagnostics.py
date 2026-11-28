
"""
Legacy Phase VII: Calibration diagnostics.

Observed marginal likelihood curvature,
parameter covariance and approximate Wald
confidence intervals for Rasch calibration.

Research-only. Does not establish item validity.
"""

import math
from collections import Counter

from cognitive_calibration import (
    calibrate_rasch,
    validate_dataset,
    quadrature_grid,
    expectation_step,
)

DIAGNOSTICS_VERSION = 1


def marginal_likelihood(
    difficulties,
    patterns,
    grid,
    log_prior,
):
    value, _, _ = expectation_step(
        patterns,
        difficulties,
        grid,
        log_prior,
    )

    return value


def observed_information(
    difficulties,
    likelihood,
    step=0.001,
):
    if (
        type(step) not in (int, float)
        or not math.isfinite(step)
        or not 0.00001 <= step <= 0.01
    ):
        raise ValueError(
            "Invalid differentiation step."
        )

    difficulties = list(difficulties)

    size = len(difficulties)

    if not size:
        raise ValueError("No parameters.")

    matrix = [
        [0.0] * size
        for _ in range(size)
    ]

    center = likelihood(difficulties)

    for i in range(size):
        plus = difficulties.copy()
        minus = difficulties.copy()

        plus[i] += step
        minus[i] -= step

        matrix[i][i] = -(
            likelihood(plus)
            - 2 * center
            + likelihood(minus)
        ) / step ** 2

        for j in range(i + 1, size):
            pp = difficulties.copy()
            pm = difficulties.copy()
            mp = difficulties.copy()
            mm = difficulties.copy()

            pp[i] += step
            pp[j] += step

            pm[i] += step
            pm[j] -= step

            mp[i] -= step
            mp[j] += step

            mm[i] -= step
            mm[j] -= step

            value = -(
                likelihood(pp)
                - likelihood(pm)
                - likelihood(mp)
                + likelihood(mm)
            ) / (4 * step ** 2)

            matrix[i][j] = value
            matrix[j][i] = value

    return matrix


def cholesky(matrix):
    size = len(matrix)

    if not size or any(
        len(row) != size
        for row in matrix
    ):
        raise ValueError(
            "Invalid matrix dimensions."
        )

    for i in range(size):
        for j in range(size):
            if not math.isfinite(matrix[i][j]):
                raise ValueError(
                    "Nonfinite matrix entry."
                )

            if not math.isclose(
                matrix[i][j],
                matrix[j][i],
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    "Matrix is not symmetric."
                )

    lower = [
        [0.0] * size
        for _ in range(size)
    ]

    scale = max(
        abs(matrix[i][i])
        for i in range(size)
    )

    if scale <= 0:
        raise ArithmeticError(
            "Invalid information matrix."
        )

    for i in range(size):
        for j in range(i + 1):
            residual = (
                matrix[i][j]
                - math.fsum(
                    lower[i][k] * lower[j][k]
                    for k in range(j)
                )
            )

            if i == j:
                if residual <= scale * 1e-12:
                    raise ArithmeticError(
                        "Information matrix is not "
                        "sufficiently positive definite."
                    )

                lower[i][j] = math.sqrt(
                    residual
                )

            else:
                lower[i][j] = (
                    residual / lower[j][j]
                )

    return lower


def invert_information(matrix):
    lower = cholesky(matrix)

    size = len(matrix)

    inverse = [
        [0.0] * size
        for _ in range(size)
    ]

    for column in range(size):
        forward = [0.0] * size

        for i in range(size):
            target = float(i == column)

            forward[i] = (
                target
                - math.fsum(
                    lower[i][k] * forward[k]
                    for k in range(i)
                )
            ) / lower[i][i]

        backward = [0.0] * size

        for i in range(size - 1, -1, -1):
            backward[i] = (
                forward[i]
                - math.fsum(
                    lower[k][i] * backward[k]
                    for k in range(i + 1, size)
                )
            ) / lower[i][i]

        for i in range(size):
            inverse[i][column] = backward[i]

    return inverse


def matrix_product(left, right):
    size = len(left)

    return [
        [
            math.fsum(
                left[i][k] * right[k][j]
                for k in range(size)
            )
            for j in range(size)
        ]
        for i in range(size)
    ]


def matrix_norm(matrix):
    return max(
        math.fsum(abs(value) for value in row)
        for row in matrix
    )


def analyze_information(matrix):
    covariance = invert_information(matrix)

    condition_estimate = (
        matrix_norm(matrix)
        * matrix_norm(covariance)
    )

    if (
        not math.isfinite(condition_estimate)
        or condition_estimate > 1e10
    ):
        raise ArithmeticError(
            "Information matrix is ill-conditioned."
        )

    product = matrix_product(
        matrix, covariance
    )

    maximum_error = max(
        abs(product[i][j] - float(i == j))
        for i in range(len(matrix))
        for j in range(len(matrix))
    )

    if maximum_error > 0.000001:
        raise ArithmeticError(
            "Covariance inversion verification failed."
        )

    standard_errors = [
        math.sqrt(covariance[i][i])
        for i in range(len(matrix))
    ]

    return {
        "covariance": covariance,
        "standard_errors": standard_errors,
        "condition_estimate": condition_estimate,
        "inverse_residual": maximum_error,
    }


def calibrate_with_diagnostics(
    item_ids,
    responses,
    *,
    grid_points=81,
    step=0.001,
):
    item_ids, responses, _ = validate_dataset(
        item_ids, responses
    )

    # Bound the computational cost of the
    # research finite-difference implementation.
    if len(item_ids) > 30:
        raise ValueError(
            "Current diagnostic limit is 30 items."
        )

    result = calibrate_rasch(
        item_ids,
        responses,
        grid_points=grid_points,
    )

    if not result["converged"]:
        raise ArithmeticError(
            "Calibration did not converge."
        )

    if any(
        item["quality_flags"]
        for item in result["items"]
    ):
        raise ArithmeticError(
            "Calibration has unresolved quality flags."
        )

    difficulties = [
        item["difficulty"]
        for item in result["items"]
    ]

    patterns = Counter(responses)

    grid, log_prior = quadrature_grid(
        grid_points
    )

    def likelihood(parameters):
        return marginal_likelihood(
            parameters,
            patterns,
            grid,
            log_prior,
        )

    information = observed_information(
        difficulties,
        likelihood,
        step=step,
    )

    diagnostics = analyze_information(
        information
    )

    refined_information = observed_information(
        difficulties,
        likelihood,
        step=step / 2,
    )

    refined = analyze_information(
        refined_information
    )

    for first, second in zip(
        diagnostics["standard_errors"],
        refined["standard_errors"],
    ):
        if not math.isclose(
            first,
            second,
            rel_tol=0.005,
            abs_tol=0.00001,
        ):
            raise ArithmeticError(
                "Numerical uncertainty estimates "
                "failed convergence verification."
            )

    z = 1.959963984540054

    for item, standard_error in zip(
        result["items"],
        refined["standard_errors"],
    ):
        difficulty = item["difficulty"]

        item["parameter_standard_error"] = (
            standard_error
        )

        item["difficulty_ci_95"] = [
            difficulty - z * standard_error,
            difficulty + z * standard_error,
        ]

        item["interval_method"] = (
            "asymptotic_wald"
        )

    result["diagnostics"] = {
        "version": DIAGNOSTICS_VERSION,
        "method": (
            "observed_marginal_likelihood_hessian"
        ),
        "information_matrix":
            refined_information,
        "parameter_covariance":
            refined["covariance"],
        "condition_estimate":
            refined["condition_estimate"],
        "inverse_residual":
            refined["inverse_residual"],
        "differentiation_step": step / 2,
        "numerical_convergence_verified": True,
        "item_fit_validated": False,
        "research_only": True,
    }

    return result


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_tests():
    from random import Random
    from cognitive_psychometrics import logistic

    def known_likelihood(parameters):
        x, y = parameters

        return -0.5 * (
            4 * x ** 2
            + 2 * x * y
            + 3 * y ** 2
        )

    information = observed_information(
        [0.0, 0.0],
        known_likelihood,
    )

    expected = [
        [4.0, 1.0],
        [1.0, 3.0],
    ]

    for actual_row, expected_row in zip(
        information, expected
    ):
        for actual, target in zip(
            actual_row, expected_row
        ):
            require(
                math.isclose(
                    actual, target,
                    abs_tol=1e-8,
                ),
                "Incorrect Hessian calculation.",
            )

    print("Analytical Hessian comparison: PASSED")

    covariance = invert_information(
        expected
    )

    known_inverse = [
        [3 / 11, -1 / 11],
        [-1 / 11, 4 / 11],
    ]

    for actual_row, expected_row in zip(
        covariance, known_inverse
    ):
        for actual, target in zip(
            actual_row, expected_row
        ):
            require(
                math.isclose(
                    actual, target,
                    abs_tol=1e-10,
                ),
                "Incorrect matrix inverse.",
            )

    print("Analytical covariance comparison: PASSED")

    invalid_matrices = (
        [[1, 1], [1, 1]],
        [[1, 2], [2, 1]],
        [[1, 0], [1, 1]],
        [[float("nan"), 0], [0, 1]],
    )

    for matrix in invalid_matrices:
        try:
            analyze_information(matrix)
        except (ValueError, ArithmeticError):
            pass
        else:
            raise AssertionError(
                "Invalid information matrix accepted."
            )

    print("Invalid information matrices: PASSED")

    rng = Random(20261128)

    true_difficulties = [
        -2.0, -1.0, 0.0, 1.0, 2.0
    ]

    item_ids = [
        f"synthetic_{i}"
        for i in range(5)
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

    result = calibrate_with_diagnostics(
        item_ids,
        responses,
    )

    print()
    print("Synthetic calibration uncertainty:")

    for true, item in zip(
        true_difficulties,
        result["items"],
    ):
        estimate = item["difficulty"]
        se = item["parameter_standard_error"]
        lower, upper = item["difficulty_ci_95"]

        require(
            math.isfinite(se) and se > 0,
            "Invalid parameter standard error.",
        )

        require(
            lower < estimate < upper,
            "Invalid confidence interval.",
        )

        print(
            f"  True: {true:+.3f} | "
            f"Estimate: {estimate:+.3f} | "
            f"SE: {se:.4f} | "
            f"95% CI: [{lower:+.3f}, "
            f"{upper:+.3f}]"
        )

    print("Parameter uncertainty estimation: PASSED")

    require(
        result["diagnostics"][
            "numerical_convergence_verified"
        ],
        "Numerical convergence not verified.",
    )

    print("Hessian resolution stability: PASSED")

    # Duplicate response patterns solely to
    # verify mathematical sample-size scaling.
    # These are not additional independent people.
    doubled = calibrate_with_diagnostics(
        item_ids,
        responses + responses,
    )

    for first, second in zip(
        result["items"],
        doubled["items"],
    ):
        require(
            math.isclose(
                first["difficulty"],
                second["difficulty"],
                abs_tol=1e-7,
            ),
            "Parameter scaling inconsistency.",
        )

        require(
            math.isclose(
                first["parameter_standard_error"]
                / math.sqrt(2),
                second["parameter_standard_error"],
                rel_tol=0.005,
            ),
            "Incorrect uncertainty scaling.",
        )

    print("Mathematical information scaling: PASSED")

    require(
        result["research_only"]
        and not result["iq_reporting_enabled"]
        and not result["scientific_approval_granted"],
        "Scientific reporting safeguards failed.",
    )

    print("Scientific reporting safeguards: PASSED")

    print()
    print("ALL CALIBRATION DIAGNOSTICS TESTS PASSED")


if __name__ == "__main__":
    run_tests()

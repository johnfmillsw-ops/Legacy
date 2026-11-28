
"""
Legacy Phase VII: Psychometric mathematics.

Research-only unidimensional dichotomous IRT.

Supports:
- Rasch / unit-slope 1PL
- 2PL
- 3PL
- Fisher information
- Conditional information-based standard error
- Expected A Posteriori estimation
- Posterior uncertainty and credible intervals

Does not calibrate item parameters or authorize
population-referenced cognitive reporting.
"""

import math

from dataclasses import dataclass

PSYCHOMETRIC_VERSION = 1


def finite_number(value, name):
    if type(value) not in (int, float):
        raise ValueError(f"Invalid {name}.")

    value = float(value)

    if not math.isfinite(value):
        raise ValueError(f"Nonfinite {name}.")

    return value


@dataclass(frozen=True)
class ItemParameters:
    difficulty: float
    discrimination: float = 1.0
    lower_asymptote: float = 0.0
    model: str = "2PL"

    def __post_init__(self):
        b = finite_number(
            self.difficulty, "difficulty"
        )

        a = finite_number(
            self.discrimination, "discrimination"
        )

        c = finite_number(
            self.lower_asymptote, "lower asymptote"
        )

        if a <= 0:
            raise ValueError(
                "Discrimination must be positive."
            )

        if not 0 <= c < 1:
            raise ValueError(
                "Lower asymptote must be in [0, 1)."
            )

        if self.model not in ("1PL", "2PL", "3PL"):
            raise ValueError("Unsupported IRT model.")

        if self.model == "1PL":
            if a != 1 or c != 0:
                raise ValueError(
                    "Unit-slope 1PL requires a=1 and c=0."
                )

        if self.model == "2PL" and c != 0:
            raise ValueError(
                "2PL requires c=0."
            )

        object.__setattr__(self, "difficulty", b)
        object.__setattr__(self, "discrimination", a)
        object.__setattr__(self, "lower_asymptote", c)


def logistic(value):
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))

    exponential = math.exp(value)

    return exponential / (1.0 + exponential)


def softplus(value):
    return max(value, 0.0) + math.log1p(
        math.exp(-abs(value))
    )


def logaddexp(left, right):
    maximum = max(left, right)

    if maximum == -math.inf:
        return maximum

    return maximum + math.log1p(
        math.exp(min(left, right) - maximum)
    )


def linear_predictor(theta, item):
    theta = finite_number(theta, "ability")

    result = item.discrimination * (
        theta - item.difficulty
    )

    if not math.isfinite(result):
        raise ValueError(
            "Nonfinite linear predictor."
        )

    return result


def log_probabilities(theta, item):
    z = linear_predictor(theta, item)

    c = item.lower_asymptote

    log_s = -softplus(-z)

    log_one_minus_s = -softplus(z)

    log_one_minus_c = math.log1p(-c)

    log_q = (
        log_one_minus_c + log_one_minus_s
    )

    if c == 0:
        log_p = log_s

    else:
        log_p = logaddexp(
            math.log(c),
            log_one_minus_c + log_s,
        )

    return log_p, log_q


def probability_correct(theta, item):
    log_p, _ = log_probabilities(
        theta, item
    )

    return math.exp(log_p)


def probability_derivative(theta, item):
    z = linear_predictor(theta, item)

    return (
        item.discrimination
        * (1.0 - item.lower_asymptote)
        * logistic(z)
        * logistic(-z)
    )


def item_information(theta, item):
    z = linear_predictor(theta, item)

    log_p, log_q = log_probabilities(
        theta, item
    )

    log_derivative = (
        math.log(item.discrimination)
        + math.log1p(-item.lower_asymptote)
        - softplus(-z)
        - softplus(z)
    )

    log_information = (
        2.0 * log_derivative
        - log_p
        - log_q
    )

    return math.exp(log_information)


def test_information(theta, items):
    items = tuple(items)

    if not items:
        raise ValueError("No item parameters.")

    return math.fsum(
        item_information(theta, item)
        for item in items
    )


def conditional_standard_error(theta, items):
    information = test_information(
        theta, items
    )

    if information <= 0:
        return math.inf

    return 1.0 / math.sqrt(information)


def validate_responses(items, responses):
    items = tuple(items)
    responses = tuple(responses)

    if not items:
        raise ValueError("No item parameters.")

    if len(items) != len(responses):
        raise ValueError(
            "Item and response counts differ."
        )

    if not all(
        isinstance(item, ItemParameters)
        for item in items
    ):
        raise ValueError("Invalid item parameters.")

    if any(
        type(response) is not int
        or response not in (0, 1)
        for response in responses
    ):
        raise ValueError(
            "Responses must be integer 0 or 1."
        )

    return items, responses


def response_log_likelihood(
    theta,
    items,
    responses,
):
    items, responses = validate_responses(
        items, responses
    )

    terms = []

    for item, response in zip(
        items, responses
    ):
        log_p, log_q = log_probabilities(
            theta, item
        )

        terms.append(
            log_p if response == 1 else log_q
        )

    return math.fsum(terms)


def posterior_quantile(
    grid,
    weights,
    probability,
):
    cumulative = 0.0

    for theta, weight in zip(grid, weights):
        cumulative += weight

        if cumulative >= probability:
            return theta

    return grid[-1]


def estimate_eap(
    items,
    responses,
    prior_mean=0.0,
    prior_sd=1.0,
    grid_min=-8.0,
    grid_max=8.0,
    grid_points=1601,
):
    items, responses = validate_responses(
        items, responses
    )

    prior_mean = finite_number(
        prior_mean, "prior mean"
    )

    prior_sd = finite_number(
        prior_sd, "prior standard deviation"
    )

    grid_min = finite_number(
        grid_min, "grid minimum"
    )

    grid_max = finite_number(
        grid_max, "grid maximum"
    )

    if prior_sd <= 0:
        raise ValueError(
            "Prior deviation must be positive."
        )

    if grid_min >= grid_max:
        raise ValueError("Invalid grid bounds.")

    if (
        type(grid_points) is not int
        or not 101 <= grid_points <= 20001
    ):
        raise ValueError("Invalid grid resolution.")

    step = (
        (grid_max - grid_min)
        / (grid_points - 1)
    )

    grid = [
        grid_min + index * step
        for index in range(grid_points)
    ]

    log_weights = []

    for index, theta in enumerate(grid):
        standardized = (
            (theta - prior_mean) / prior_sd
        )

        log_prior = (
            -0.5 * standardized ** 2
        )

        log_likelihood = response_log_likelihood(
            theta, items, responses
        )

        log_weight = (
            log_prior + log_likelihood
        )

        # Trapezoidal numerical integration.
        if index in (0, grid_points - 1):
            log_weight += math.log(0.5)

        log_weights.append(log_weight)

    maximum = max(log_weights)

    if not math.isfinite(maximum):
        raise ArithmeticError(
            "Posterior normalization failed."
        )

    weights = [
        math.exp(value - maximum)
        for value in log_weights
    ]

    denominator = math.fsum(weights)

    weights = [
        weight / denominator
        for weight in weights
    ]

    # Reject potentially truncated posteriors.
    edge_count = max(1, grid_points // 100)

    edge_mass = (
        math.fsum(weights[:edge_count])
        + math.fsum(weights[-edge_count:])
    )

    if edge_mass > 0.0001:
        raise ArithmeticError(
            "Posterior grid appears truncated. "
            "Expand integration bounds."
        )

    estimate = math.fsum(
        theta * weight
        for theta, weight in zip(grid, weights)
    )

    variance = math.fsum(
        weight * (theta - estimate) ** 2
        for theta, weight in zip(grid, weights)
    )

    lower = posterior_quantile(
        grid, weights, 0.025
    )

    upper = posterior_quantile(
        grid, weights, 0.975
    )

    return {
        "psychometric_version": PSYCHOMETRIC_VERSION,
        "method": "EAP",
        "research_only": True,
        "theta": estimate,
        "posterior_sd": math.sqrt(variance),
        "credible_interval_95": [lower, upper],
        "test_information": test_information(
            estimate, items
        ),
        "conditional_standard_error":
            conditional_standard_error(
                estimate, items
            ),
        "prior_mean": prior_mean,
        "prior_sd": prior_sd,
        "items_answered": len(responses),
        "grid_step": step,
        "posterior_edge_mass": edge_mass,
        "iq_reporting_enabled": False,
    }


def close(actual, expected, tolerance=1e-9):
    if not math.isclose(
        actual,
        expected,
        rel_tol=tolerance,
        abs_tol=tolerance,
    ):
        raise AssertionError(
            f"Expected {expected}; got {actual}"
        )


def run_tests():
    from random import Random

    rasch = ItemParameters(
        difficulty=0,
        model="1PL",
    )

    two_pl = ItemParameters(
        difficulty=0,
        discrimination=2,
        model="2PL",
    )

    three_pl = ItemParameters(
        difficulty=0,
        discrimination=1.5,
        lower_asymptote=0.2,
        model="3PL",
    )

    close(
        probability_correct(0, rasch),
        0.5,
    )

    close(
        probability_correct(0, two_pl),
        0.5,
    )

    close(
        probability_correct(0, three_pl),
        0.6,
    )

    print("Known probability values: PASSED")

    close(item_information(0, rasch), 0.25)

    close(item_information(0, two_pl), 1.0)

    close(
        item_information(0, three_pl),
        0.375,
    )

    print("Known information values: PASSED")

    close(
        test_information(0, [rasch] * 16),
        4.0,
    )

    close(
        conditional_standard_error(
            0, [rasch] * 16
        ),
        0.5,
    )

    print("Test information and standard error: PASSED")

    rng = Random(20261128)

    for index in range(10000):
        model = rng.choice(
            ("1PL", "2PL", "3PL")
        )

        item = ItemParameters(
            difficulty=rng.uniform(-3, 3),
            discrimination=(
                1.0 if model == "1PL"
                else rng.uniform(0.3, 3.0)
            ),
            lower_asymptote=(
                rng.uniform(0, 0.35)
                if model == "3PL"
                else 0.0
            ),
            model=model,
        )

        theta = rng.uniform(-4, 4)

        probability = probability_correct(
            theta, item
        )

        direct_probability = (
            item.lower_asymptote
            + (1 - item.lower_asymptote)
            / (
                1 + math.exp(
                    -item.discrimination
                    * (theta - item.difficulty)
                )
            )
        )

        close(
            probability,
            direct_probability,
        )

        h = 0.00001

        numerical_derivative = (
            probability_correct(theta + h, item)
            - probability_correct(theta - h, item)
        ) / (2 * h)

        close(
            probability_derivative(theta, item),
            numerical_derivative,
            tolerance=1e-7,
        )

        numerical_information = (
            numerical_derivative ** 2
            / (
                probability
                * (1 - probability)
            )
        )

        close(
            item_information(theta, item),
            numerical_information,
            tolerance=1e-6,
        )

    print(
        "10,000 numerical cross-checks: PASSED"
    )

    for theta in (-1000, -100, 100, 1000):
        for item in (rasch, two_pl, three_pl):
            log_p, log_q = log_probabilities(
                theta, item
            )

            assert math.isfinite(log_p)
            assert math.isfinite(log_q)

            assert item_information(
                theta, item
            ) >= 0

    print("Extreme ability numerical stability: PASSED")

    items = [rasch] * 20

    balanced = estimate_eap(
        items,
        [1, 0] * 10,
    )

    close(balanced["theta"], 0.0)

    print("Symmetric posterior estimation: PASSED")

    low = estimate_eap(
        items, [0] * 20
    )

    high = estimate_eap(
        items, [1] * 20
    )

    assert low["theta"] < 0
    assert high["theta"] > 0

    close(
        high["theta"],
        -low["theta"],
    )

    print("Extreme response patterns: PASSED")

    previous = -math.inf

    for correct in (0, 5, 10, 15, 20):
        result = estimate_eap(
            items,
            [1] * correct
            + [0] * (20 - correct),
        )

        assert result["theta"] > previous

        previous = result["theta"]

    print("Ability monotonicity: PASSED")

    short = estimate_eap(
        [rasch] * 4,
        [1, 0, 1, 0],
    )

    long = estimate_eap(
        [rasch] * 80,
        [1, 0] * 40,
    )

    assert long["posterior_sd"] < (
        short["posterior_sd"]
    )

    print("Measurement precision behavior: PASSED")

    refined = estimate_eap(
        items,
        [1] * 15 + [0] * 5,
        grid_points=3201,
    )

    original = estimate_eap(
        items,
        [1] * 15 + [0] * 5,
    )

    close(
        refined["theta"],
        original["theta"],
        tolerance=1e-7,
    )

    close(
        refined["posterior_sd"],
        original["posterior_sd"],
        tolerance=1e-7,
    )

    print("Numerical integration convergence: PASSED")

    invalid_cases = (
        lambda: ItemParameters(0, 0),
        lambda: ItemParameters(0, -1),
        lambda: ItemParameters(float("nan")),
        lambda: ItemParameters(0, 1, 1, "3PL"),
        lambda: ItemParameters(0, 2, 0, "1PL"),
        lambda: ItemParameters(0, 1, 0.2, "2PL"),
        lambda: estimate_eap([], []),
        lambda: estimate_eap([rasch], [2]),
        lambda: estimate_eap([rasch], [True]),
        lambda: estimate_eap([rasch], [0, 1]),
        lambda: estimate_eap([rasch], [1], prior_sd=0),
    )

    for operation in invalid_cases:
        try:
            operation()
        except (ValueError, ArithmeticError):
            pass
        else:
            raise AssertionError(
                "Invalid psychometric input accepted."
            )

    print("11 invalid-input controls: PASSED")

    try:
        estimate_eap(
            items,
            [1] * 20,
            grid_min=-1,
            grid_max=1,
        )
    except ArithmeticError:
        print("Posterior truncation detection: PASSED")
    else:
        raise AssertionError(
            "Truncated posterior accepted."
        )

    assert original["research_only"] is True

    assert original["iq_reporting_enabled"] is False

    print("Research-only reporting status: PASSED")

    print()
    print("ALL PSYCHOMETRIC MATHEMATICS TESTS PASSED")


if __name__ == "__main__":
    run_tests()

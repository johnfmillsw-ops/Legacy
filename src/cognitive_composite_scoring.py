
"""
Legacy Phase VII: Theoretical composite cognitive scoring.

Produces an IQ-scale cognitive index using explicitly
uncalibrated Bayesian domain ability estimates.

Not a population-normed intelligence measurement.
"""

from math import fsum, isfinite, isclose

from cognitive_engine import fingerprint

from cognitive_domain_scoring import (
    UNTIMED_DOMAINS,
    score_untimed_domains,
)

from cognitive_speed_scoring import (
    score_processing_speed,
)

from cognitive_scoring_parameters import (
    parameter_model_id,
)


COMPOSITE_SCORING_VERSION = 2

REFERENCE_CENTER = 100.0
REFERENCE_SCALE = 15.0

DOMAIN_WEIGHTS = {
    domain: 0.20
    for domain in UNTIMED_DOMAINS
}


def scoring_manifest():

    return {
        "scoring_version":
            COMPOSITE_SCORING_VERSION,
        "method":
            "equal_weight_theoretical_rasch_ability",
        "parameter_model_id":
            parameter_model_id(),
        "domain_weights":
            dict(DOMAIN_WEIGHTS),
        "reference_center":
            REFERENCE_CENTER,
        "reference_scale":
            REFERENCE_SCALE,
        "reference_type":
            "assumed_latent_scale",
        "processing_speed_in_composite":
            False,
        "population_normed":
            False,
        "scientifically_validated":
            False,
        "population_percentile_available":
            False,
        "validated_confidence_interval_available":
            False,
    }


def scoring_model_id():

    return fingerprint(scoring_manifest())


def ability_to_scale(theta):

    if (
        type(theta) not in (int, float)
        or not isfinite(theta)
    ):
        raise ValueError(
            "Invalid latent ability estimate."
        )

    return REFERENCE_CENTER + REFERENCE_SCALE * theta


def combine_domain_estimates(domain_results):

    if set(domain_results) != set(UNTIMED_DOMAINS):
        raise ValueError(
            "Incomplete cognitive domain inventory."
        )

    if not isclose(
        fsum(DOMAIN_WEIGHTS.values()),
        1.0,
        abs_tol=1e-12,
    ):
        raise RuntimeError(
            "Invalid composite domain weights."
        )

    weighted = []
    domains = {}

    for domain in UNTIMED_DOMAINS:

        result = domain_results[domain]

        if result["domain"] != domain:
            raise ValueError(
                "Domain identity mismatch."
            )

        if result["item_count"] != 12:
            raise ValueError(
                "Incomplete domain administration."
            )

        if (
            result["parameter_model_id"]
            != parameter_model_id()
        ):
            raise ValueError(
                "Scoring parameter version mismatch."
            )

        estimate = result["ability_estimate"]

        theta = estimate["theta"]

        scale_score = ability_to_scale(theta)

        posterior_sd = estimate["posterior_sd"]

        if (
            type(posterior_sd) not in (int, float)
            or not isfinite(posterior_sd)
            or posterior_sd <= 0
        ):
            raise ValueError(
                "Invalid posterior uncertainty."
            )

        weighted.append(
            DOMAIN_WEIGHTS[domain] * theta
        )

        domains[domain] = {
            **result,
            "theoretical_scale_score":
                round(scale_score, 2),
            "composite_weight":
                DOMAIN_WEIGHTS[domain],
        }

    composite_theta = fsum(weighted)

    composite_score = ability_to_scale(
        composite_theta
    )

    return {
        "composite_theta": composite_theta,
        "theoretical_iq_scale_score":
            round(composite_score, 2),
        "display_score":
            round(composite_score),
        "domain_results": domains,
        "scoring_version":
            COMPOSITE_SCORING_VERSION,
        "scoring_model_id":
            scoring_model_id(),
        "scoring_methodology":
            scoring_manifest(),
        "reporting_status":
            "theoretical_index",
        "population_normed": False,
        "scientifically_validated": False,
        "population_percentile": None,
        "validated_iq_interval": None,
    }


def score_completed_assessment(session):

    if session.state != "completed":
        raise ValueError(
            "Assessment must be completed."
        )

    if session.interruptions:
        raise ValueError(
            "Interrupted administration cannot "
            "produce a composite score."
        )

    domain_results = score_untimed_domains(
        session
    )

    composite = combine_domain_estimates(
        domain_results
    )

    speed = score_processing_speed(session)

    composite["domain_results"][
        "processing_speed"
    ] = {
        **speed,
        "composite_weight": 0.0,
        "theoretical_scale_score": None,
    }

    composite["assessment_id"] = (
        session.session_id
    )

    composite["form_id"] = session.form_id

    return composite


def require(condition, message):

    if not condition:
        raise AssertionError(message)


def run_tests():

    from copy import deepcopy

    from cognitive_research_bank import (
        build_research_bank,
    )

    from cognitive_blueprint import (
        assemble_assessment,
    )

    from cognitive_session import (
        AssessmentSession,
    )

    from test_cognitive_database import (
        complete_session,
    )

    require(
        ability_to_scale(0) == 100
        and ability_to_scale(1) == 115
        and ability_to_scale(-1) == 85,
        "Incorrect scale conversion.",
    )

    print("Analytical scale conversion: PASSED")

    bank = build_research_bank()

    form = assemble_assessment(
        bank,
        "composite-scoring-verification-v1",
    )

    session = AssessmentSession(
        form, bank, 1000
    )

    try:
        score_completed_assessment(session)
    except ValueError:
        print("Incomplete assessment rejection: PASSED")
    else:
        raise AssertionError(
            "Incomplete assessment was scored."
        )

    complete_session(session)

    result = score_completed_assessment(
        session
    )

    require(
        len(result["domain_results"]) == 6,
        "Incomplete domain reporting.",
    )

    print("Six-domain results integration: PASSED")

    require(
        result["domain_results"][
            "processing_speed"
        ]["composite_weight"] == 0.0,
        "Unsupported speed conversion.",
    )

    print("Processing speed separation: PASSED")

    domains = score_untimed_domains(session)

    expected_theta = fsum(
        item["ability_estimate"]["theta"]
        for item in domains.values()
    ) / 5

    require(
        isclose(
            result["composite_theta"],
            expected_theta,
            abs_tol=1e-12,
        ),
        "Incorrect composite weighting.",
    )

    print("Equal-weight composite calculation: PASSED")

    require(
        result["theoretical_iq_scale_score"]
        == round(
            100 + 15 * expected_theta,
            2,
        ),
        "Incorrect numerical score.",
    )

    print("Numerical cognitive score: PASSED")

    # Synthetic mathematical fixtures.
    # These do not represent human norming data.

    def synthetic_domains(theta):

        data = deepcopy(domains)

        for item in data.values():
            item["ability_estimate"]["theta"] = theta

        return data

    for theta, expected in (
        (-2, 70),
        (-1, 85),
        (0, 100),
        (1, 115),
        (2, 130),
    ):

        scored = combine_domain_estimates(
            synthetic_domains(theta)
        )

        require(
            scored["display_score"] == expected,
            "Synthetic scale conversion failed.",
        )

    print("Five analytical scoring fixtures: PASSED")

    lower = synthetic_domains(0)
    higher = synthetic_domains(0)

    higher["fluid_reasoning"][
        "ability_estimate"
    ]["theta"] = 1.0

    require(
        combine_domain_estimates(
            higher
        )["display_score"]
        >
        combine_domain_estimates(
            lower
        )["display_score"],
        "Composite monotonicity failed.",
    )

    print("Composite monotonicity: PASSED")

    def expect_rejection(data, label):

        try:
            combine_domain_estimates(data)
        except ValueError:
            print(label + ": PASSED")
        else:
            raise AssertionError(
                "Invalid composite data accepted."
            )

    missing = deepcopy(domains)
    del missing["working_memory"]

    expect_rejection(
        missing,
        "Missing domain rejection",
    )

    corrupted = deepcopy(domains)

    corrupted["fluid_reasoning"][
        "parameter_model_id"
    ] = "invalid"

    expect_rejection(
        corrupted,
        "Parameter version mismatch rejection",
    )

    corrupted = synthetic_domains(float("nan"))

    expect_rejection(
        corrupted,
        "Nonfinite ability rejection",
    )

    require(
        result["population_normed"] is False
        and result["scientifically_validated"] is False
        and result["population_percentile"] is None
        and result["validated_iq_interval"] is None,
        "Unsupported scientific reporting.",
    )

    print("Scientific reporting safeguards: PASSED")

    require(
        score_completed_assessment(session) == result,
        "Scoring reproducibility failed.",
    )

    print("Deterministic composite scoring: PASSED")

    print()
    print("SYNTHETIC ASSESSMENT RESULTS")
    print()

    for domain, data in result[
        "domain_results"
    ].items():

        print(
            domain,
            data["theoretical_scale_score"],
        )

    print()
    print(
        "Theoretical IQ-scale score:",
        result["theoretical_iq_scale_score"],
    )

    print(
        "Displayed numerical score:",
        result["display_score"],
    )

    print(
        "Processing speed, correct per minute:",
        result["domain_results"][
            "processing_speed"
        ]["correct_per_minute"],
    )

    print()
    print("Scoring model:", scoring_model_id())
    print()
    print("ALL COMPOSITE SCORING TESTS PASSED")


if __name__ == "__main__":
    run_tests()

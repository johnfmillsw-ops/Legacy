
"""
Legacy Phase VII: Scientific measurement policy.

Defines evidence requirements for cognitive reporting.
Software verification is not psychometric validation.

Research foundations:
https://www.apa.org/science/programs/testing/standards
https://doi.org/10.1016/j.intell.2014.01.004
https://doi.org/10.7910/DVN/AD9RVY
https://doi.org/10.3390/jintelligence13120154
"""

from copy import deepcopy

POLICY_VERSION = 1

QUALIFICATION_STAGES = (
    "experimental",
    "content_reviewed",
    "empirically_calibrated",
    "validated",
    "norm_referenced",
)

CONSTRUCTS = {
    "fluid_reasoning": {
        "construct": "Fluid reasoning",
        "chc_reference": "Gf",
    },
    "visual_spatial": {
        "construct": "Visual processing",
        "chc_reference": "Gv",
    },
    "verbal_comprehension": {
        "construct": "Comprehension knowledge",
        "chc_reference": "Gc",
    },
    "quantitative_reasoning": {
        "construct": "Quantitative knowledge",
        "chc_reference": "Gq",
    },
    "working_memory": {
        "construct": "Working memory capacity",
        "chc_reference": "Gwm",
    },
    "processing_speed": {
        "construct": "Processing speed",
        "chc_reference": "Gs",
    },
}

EVIDENCE_REQUIREMENTS = {
    "content_reviewed": (
        "construct_definition",
        "independent_content_review",
        "ambiguity_review",
        "accessibility_review",
    ),

    "empirically_calibrated": (
        "human_response_dataset",
        "sampling_method",
        "calibration_method",
        "item_parameter_estimates",
        "parameter_uncertainty",
        "model_fit_analysis",
        "local_dependence_analysis",
        "cross_validation",
    ),

    "validated": (
        "internal_structure_analysis",
        "reliability_analysis",
        "test_retest_analysis",
        "convergent_validity",
        "discriminant_validity",
        "response_process_analysis",
        "measurement_precision",
        "fairness_analysis",
        "practice_effect_analysis",
        "administration_standardization",
        "alternate_form_comparability",
        "independent_professional_review",
    ),

    "norm_referenced": (
        "normative_population_definition",
        "normative_sampling_method",
        "age_adjustment_method",
        "normative_sample_analysis",
        "score_conversion_method",
        "normative_uncertainty_analysis",
        "composite_score_validation",
        "independent_normative_review",
    ),
}

EXPERIMENTAL_METRICS = (
    "items_answered",
    "correct_responses",
    "incorrect_responses",
    "raw_accuracy",
    "observed_response_latency",
    "practice_history",
)

RESTRICTED_METRICS = (
    "iq",
    "estimated_iq",
    "population_percentile",
    "age_adjusted_standard_score",
    "standardized_domain_score",
    "general_intelligence_score",
    "clinical_classification",
    "diagnosis",
)


def get_measurement_policy():
    return {
        "policy_version": POLICY_VERSION,
        "qualification_status": "experimental",
        "constructs": deepcopy(CONSTRUCTS),
        "qualification_stages": list(
            QUALIFICATION_STAGES
        ),
        "evidence_requirements": deepcopy(
            EVIDENCE_REQUIREMENTS
        ),
        "permitted_metrics": list(
            EXPERIMENTAL_METRICS
        ),
        "restricted_metrics": list(
            RESTRICTED_METRICS
        ),
        "iq_reporting_enabled": False,
        "clinical_reporting_enabled": False,
    }


def required_evidence(stage):
    if stage not in QUALIFICATION_STAGES:
        raise ValueError(
            "Unknown qualification stage."
        )

    requirements = []

    for current in QUALIFICATION_STAGES[1:]:
        if stage == "experimental":
            break

        requirements.extend(
            EVIDENCE_REQUIREMENTS[current]
        )

        if current == stage:
            break

    return tuple(requirements)


def missing_evidence(stage, evidence):
    if not isinstance(evidence, dict):
        raise TypeError(
            "Evidence must be a dictionary."
        )

    missing = []

    for requirement in required_evidence(stage):
        record = evidence.get(requirement)

        if not isinstance(record, dict):
            missing.append(requirement)
            continue

        reference = record.get("reference")

        if (
            not isinstance(reference, str)
            or not reference.strip()
        ):
            missing.append(requirement)

    return tuple(missing)


def check_evidence_inventory(stage, evidence):
    missing = missing_evidence(stage, evidence)

    return {
        "requested_stage": stage,
        "inventory_complete": not missing,
        "missing_requirements": list(missing),
        "qualification_status": "experimental",
        "scientific_approval_granted": False,
    }


def require_permitted_metric(metric):
    if metric not in EXPERIMENTAL_METRICS:
        raise PermissionError(
            f"Metric is not authorized: {metric}"
        )

    return True


def require_iq_reporting():
    raise PermissionError(
        "IQ reporting requires independently "
        "validated measurement and population norms."
    )


def require_clinical_reporting():
    raise PermissionError(
        "Clinical reporting is not authorized "
        "for this experimental instrument."
    )


def run_tests():
    policy = get_measurement_policy()

    assert len(policy["constructs"]) == 6

    assert policy["qualification_status"] == (
        "experimental"
    )

    assert not policy["iq_reporting_enabled"]
    assert not policy["clinical_reporting_enabled"]

    print("Scientific policy initialization: PASSED")

    previous = set()

    for stage in QUALIFICATION_STAGES:
        current = set(required_evidence(stage))

        assert previous <= current
        previous = current

    print("Cumulative evidence requirements: PASSED")

    for stage in QUALIFICATION_STAGES[1:]:
        result = check_evidence_inventory(
            stage, {}
        )

        assert not result["inventory_complete"]
        assert result["missing_requirements"]
        assert not result["scientific_approval_granted"]

    print("Missing evidence detection: PASSED")

    fabricated = {
        requirement: True
        for requirement in required_evidence(
            "norm_referenced"
        )
    }

    result = check_evidence_inventory(
        "norm_referenced", fabricated
    )

    assert not result["inventory_complete"]

    print("Unsupported evidence flags rejected: PASSED")

    placeholders = {
        requirement: {
            "reference": "synthetic-test-reference"
        }
        for requirement in required_evidence(
            "norm_referenced"
        )
    }

    result = check_evidence_inventory(
        "norm_referenced", placeholders
    )

    assert result["inventory_complete"]

    assert result["qualification_status"] == (
        "experimental"
    )

    assert not result["scientific_approval_granted"]

    print(
        "Evidence inventory cannot grant "
        "scientific approval: PASSED"
    )

    for metric in EXPERIMENTAL_METRICS:
        assert require_permitted_metric(metric)

    print("Experimental reporting authorization: PASSED")

    for metric in RESTRICTED_METRICS + ("unknown",):
        try:
            require_permitted_metric(metric)
        except PermissionError:
            pass
        else:
            raise AssertionError(
                f"Restricted metric allowed: {metric}"
            )

    print("Restricted metric authorization: PASSED")

    for guard in (
        require_iq_reporting,
        require_clinical_reporting,
    ):
        try:
            guard()
        except PermissionError:
            pass
        else:
            raise AssertionError(
                "Unauthorized reporting enabled."
            )

    print("IQ and clinical reporting safeguards: PASSED")

    policy["constructs"].clear()

    assert len(
        get_measurement_policy()["constructs"]
    ) == 6

    print("Policy mutation isolation: PASSED")

    print()
    print("ALL 9 SCIENTIFIC POLICY TESTS PASSED")


if __name__ == "__main__":
    run_tests()

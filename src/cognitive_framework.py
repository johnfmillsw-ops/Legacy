"""
Legacy Phase VII: Cognitive Identity.

Foundational cognitive assessment framework.
Original research instrument under development.
Not a validated clinical intelligence test.
"""

FRAMEWORK_VERSION = 1
SCORING_VERSION = 1

INSTRUMENT_ID = "legacy_cognitive_assessment"
INSTRUMENT_VERSION = 1

VALIDATION_STATUS = "experimental"

COGNITIVE_DOMAINS = {
    "fluid_reasoning": {
        "label": "Fluid Reasoning",
        "description": (
            "Identifying relationships, discovering rules "
            "and solving unfamiliar problems."
        ),
        "families": (
            "abstract_matrices",
            "logical_sequences",
            "deductive_reasoning",
        ),
    },
    "visual_spatial": {
        "label": "Visual-Spatial Ability",
        "description": (
            "Understanding spatial relationships and "
            "mentally transforming visual objects."
        ),
        "families": (
            "mental_rotation",
            "spatial_transformation",
            "spatial_relationships",
        ),
    },
    "verbal_comprehension": {
        "label": "Verbal Comprehension",
        "description": (
            "Understanding language, concepts and "
            "semantic relationships."
        ),
        "families": (
            "verbal_analogies",
            "semantic_relationships",
            "concept_classification",
        ),
    },
    "quantitative_reasoning": {
        "label": "Quantitative Reasoning",
        "description": (
            "Identifying numerical relationships and "
            "applying mathematical reasoning."
        ),
        "families": (
            "number_sequences",
            "quantitative_relationships",
            "mathematical_logic",
        ),
    },
    "working_memory": {
        "label": "Working Memory",
        "description": (
            "Temporarily maintaining and manipulating "
            "information during cognitive tasks."
        ),
        "families": (
            "sequence_recognition",
            "spatial_memory",
            "sequence_manipulation",
        ),
    },
    "processing_speed": {
        "label": "Processing Speed",
        "description": (
            "Rapid and accurate identification and "
            "comparison of visual information."
        ),
        "families": (
            "symbol_comparison",
            "visual_discrimination",
            "pattern_matching",
        ),
    },
}

ASSESSMENT_MODES = {
    "practice": {
        "label": "Cognitive Training",
        "adaptive": True,
        "immediate_feedback": True,
        "contributes_to_iq": False,
    },
    "assessment": {
        "label": "Cognitive Assessment",
        "adaptive": False,
        "immediate_feedback": False,
        "contributes_to_iq": False,
    },
}

DIFFICULTY_LEVELS = {
    1: "Foundational",
    2: "Intermediate",
    3: "Advanced",
    4: "Expert",
    5: "Highly Complex",
}

QUESTION_FORMAT = {
    "type": "single_select",
    "minimum_options": 4,
    "maximum_options": 6,
    "correct_answers": 1,
}

ASSESSMENT_BLUEPRINT = {
    "status": "provisional",
    "items_per_domain": 12,
    "target_items": 72,
    "target_duration_minutes": 45,
    "minimum_age": 18,
    "language": "en",
}

VALIDATION_REQUIREMENTS = (
    "item_difficulty_calibration",
    "item_discrimination_calibration",
    "guessing_parameter_evaluation",
    "population_norms",
    "age_adjusted_norms",
    "construct_validity",
    "criterion_validity",
    "internal_consistency",
    "test_retest_reliability",
    "alternate_form_equivalence",
    "measurement_invariance",
    "practice_effect_evaluation",
    "measurement_uncertainty",
    "independent_professional_review",
)

IQ_REPORTING_ENABLED = False


def get_framework():
    """Return an independent copy of the public framework."""
    from copy import deepcopy

    return deepcopy({
        "framework_version": FRAMEWORK_VERSION,
        "scoring_version": SCORING_VERSION,
        "instrument_id": INSTRUMENT_ID,
        "instrument_version": INSTRUMENT_VERSION,
        "validation_status": VALIDATION_STATUS,
        "domains": COGNITIVE_DOMAINS,
        "modes": ASSESSMENT_MODES,
        "difficulty_levels": DIFFICULTY_LEVELS,
        "question_format": QUESTION_FORMAT,
        "assessment_blueprint": ASSESSMENT_BLUEPRINT,
        "iq_reporting_enabled": IQ_REPORTING_ENABLED,
    })


def validate_domain(domain):
    if not isinstance(domain, str):
        raise ValueError("Invalid cognitive domain.")
    if domain not in COGNITIVE_DOMAINS:
        raise ValueError("Unknown cognitive domain.")
    return domain


def validate_difficulty(level):
    if type(level) is not int:
        raise ValueError("Difficulty must be an integer.")
    if level not in DIFFICULTY_LEVELS:
        raise ValueError("Unknown difficulty level.")
    return level


def validate_mode(mode):
    if not isinstance(mode, str):
        raise ValueError("Invalid assessment mode.")
    if mode not in ASSESSMENT_MODES:
        raise ValueError("Unknown assessment mode.")
    return mode


def require_validated_iq_reporting():
    """Fail closed until a validated scoring system exists."""
    raise RuntimeError(
        "IQ reporting is unavailable: this instrument "
        "has not been psychometrically validated."
    )


def run_self_tests():
    assert len(COGNITIVE_DOMAINS) == 6
    print("Six cognitive domains: PASSED")

    families = [
        family
        for domain in COGNITIVE_DOMAINS.values()
        for family in domain["families"]
    ]

    assert len(families) == 18
    assert len(families) == len(set(families))
    print("18 unique question families: PASSED")

    assert QUESTION_FORMAT["type"] == "single_select"
    assert QUESTION_FORMAT["correct_answers"] == 1
    print("Multiple-choice specification: PASSED")

    assert (
        len(COGNITIVE_DOMAINS)
        * ASSESSMENT_BLUEPRINT["items_per_domain"]
        == ASSESSMENT_BLUEPRINT["target_items"]
    )
    print("Assessment blueprint: PASSED")

    for domain in COGNITIVE_DOMAINS:
        assert validate_domain(domain) == domain

    for level in DIFFICULTY_LEVELS:
        assert validate_difficulty(level) == level

    for mode in ASSESSMENT_MODES:
        assert validate_mode(mode) == mode

    print("Valid framework parameters: PASSED")

    invalid_cases = (
        (validate_domain, "unknown"),
        (validate_domain, None),
        (validate_domain, []),
        (validate_difficulty, 0),
        (validate_difficulty, 6),
        (validate_difficulty, True),
        (validate_difficulty, 2.5),
        (validate_mode, "unknown"),
        (validate_mode, None),
    )

    for validator, value in invalid_cases:
        try:
            validator(value)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Invalid parameter accepted."
            )

    print("Invalid parameter rejection: PASSED")

    framework = get_framework()
    framework["domains"].clear()
    assert len(COGNITIVE_DOMAINS) == 6
    print("Framework isolation: PASSED")

    assert not ASSESSMENT_MODES["practice"]["contributes_to_iq"]
    assert not ASSESSMENT_MODES["assessment"]["contributes_to_iq"]
    print("Unvalidated scoring isolation: PASSED")

    assert IQ_REPORTING_ENABLED is False

    try:
        require_validated_iq_reporting()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Unvalidated IQ reporting allowed.")

    print("IQ validation safeguard: PASSED")

    print()
    print("ALL 9 COGNITIVE FRAMEWORK TESTS PASSED")


if __name__ == "__main__":
    run_self_tests()

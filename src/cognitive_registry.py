
"""
Legacy Phase VII: Unified cognitive registry.

Centralized generation, runtime verification,
exposure filtering and safe presentation.
"""

from copy import deepcopy

import cognitive_quantitative as quantitative
import cognitive_matrices as matrices
import cognitive_fluid as fluid
import cognitive_spatial as spatial
import cognitive_verbal as verbal
import cognitive_memory as memory
import cognitive_speed as speed

from test_cognitive_quantitative import (
    verify_question as verify_quantitative,
)

from cognitive_framework import (
    COGNITIVE_DOMAINS,
    validate_difficulty,
)

from cognitive_engine import (
    FAMILY_DOMAINS,
    create_seed,
    public_question,
    score_response,
    fingerprint,
)

REGISTRY_VERSION = 1

MAX_GENERATION_ATTEMPTS = 128

GENERATORS = {}
VERIFIERS = {}


class CognitiveGenerationError(RuntimeError):
    pass


class QuestionPoolExhausted(
    CognitiveGenerationError
):
    pass


class QuestionValidationError(
    CognitiveGenerationError
):
    pass


def register(family, generator, verifier):
    if family in GENERATORS:
        raise RuntimeError(
            f"Duplicate registration: {family}"
        )

    if family not in FAMILY_DOMAINS:
        raise RuntimeError(
            f"Unknown framework family: {family}"
        )

    if not callable(generator):
        raise TypeError("Invalid generator.")

    if not callable(verifier):
        raise TypeError("Invalid verifier.")

    GENERATORS[family] = generator
    VERIFIERS[family] = verifier


for family, generator in quantitative.GENERATORS.items():
    register(
        family,
        generator,
        verify_quantitative,
    )


register(
    "abstract_matrices",
    matrices.generate_matrix,
    matrices.verify_matrix,
)


for module in (fluid, spatial):
    for family, generator in module.GENERATORS.items():
        register(
            family,
            generator,
            module.VERIFIERS[family],
        )


for module in (verbal, memory, speed):
    for family, generator in module.GENERATORS.items():
        register(
            family,
            generator,
            module.verify_question,
        )


if set(GENERATORS) != set(FAMILY_DOMAINS):
    raise RuntimeError(
        "Registry does not match cognitive framework."
    )


MEMORY_FAMILIES = frozenset(
    memory.GENERATORS
)


def get_registry():
    return {
        "registry_version": REGISTRY_VERSION,
        "domains": {
            domain: sorted(
                family
                for family, assigned_domain
                in FAMILY_DOMAINS.items()
                if assigned_domain == domain
            )
            for domain in COGNITIVE_DOMAINS
        },
        "family_count": len(GENERATORS),
        "iq_reporting_enabled": False,
    }


def exposure_fingerprint(question):
    """
    Identify previously presented problems.

    Classification items require their options
    to distinguish actual presented questions.
    """

    if question["family"] == "concept_classification":
        return fingerprint({
            "prompt_hash": question["prompt_hash"],
            "options": sorted(
                option["value"]
                for option in question["options"]
            ),
        })

    return question["prompt_hash"]


def validate_question(question):
    family = question.get("family")

    if family not in VERIFIERS:
        raise QuestionValidationError(
            "Unknown question family."
        )

    if question.get("domain") != FAMILY_DOMAINS[family]:
        raise QuestionValidationError(
            "Incorrect cognitive domain."
        )

    validate_difficulty(
        question["difficulty"]
    )

    options = question.get("options")

    if not isinstance(options, list):
        raise QuestionValidationError(
            "Invalid question options."
        )

    if not 4 <= len(options) <= 6:
        raise QuestionValidationError(
            "Invalid number of options."
        )

    ids = [
        option["id"]
        for option in options
    ]

    values = [
        " ".join(
            option["value"].casefold().split()
        )
        for option in options
    ]

    if len(set(ids)) != len(ids):
        raise QuestionValidationError(
            "Duplicate option identifiers."
        )

    if len(set(values)) != len(values):
        raise QuestionValidationError(
            "Duplicate answer options."
        )

    if question["correct_option_id"] not in ids:
        raise QuestionValidationError(
            "Invalid answer key."
        )

    if question.get("calibration_status") != "uncalibrated":
        raise QuestionValidationError(
            "Unsupported calibration status."
        )

    try:
        result = VERIFIERS[family](question)

        if result is False:
            raise ValueError(
                "Verifier rejected question."
            )

    except Exception as exc:
        raise QuestionValidationError(
            f"Runtime verification failed: {family}"
        ) from exc

    return True


def generate_question(
    family,
    difficulty,
    seed=None,
    excluded_exposures=None,
    max_attempts=MAX_GENERATION_ATTEMPTS,
):
    if family not in GENERATORS:
        raise ValueError(
            "Unknown cognitive question family."
        )

    validate_difficulty(difficulty)

    if type(max_attempts) is not int:
        raise ValueError(
            "Invalid generation attempt limit."
        )

    if not 1 <= max_attempts <= 1000:
        raise ValueError(
            "Invalid generation attempt limit."
        )

    excluded = set(
        excluded_exposures or ()
    )

    if seed is None:
        seed = create_seed()

    for attempt in range(max_attempts):
        candidate_seed = (
            seed if attempt == 0
            else fingerprint({
                "seed": seed,
                "attempt": attempt,
                "family": family,
                "difficulty": difficulty,
            })
        )

        question = GENERATORS[family](
            difficulty,
            candidate_seed,
        )

        validate_question(question)

        exposure = exposure_fingerprint(
            question
        )

        if exposure in excluded:
            continue

        question["exposure_hash"] = exposure

        question["registry_version"] = (
            REGISTRY_VERSION
        )

        return question

    raise QuestionPoolExhausted(
        f"No unseen question found for {family} "
        f"at level {difficulty} after "
        f"{max_attempts} attempts."
    )


def presentation_question(question):
    if question["family"] in MEMORY_FAMILIES:
        return memory.presentation_payload(
            question
        )

    return public_question(question)


def response_question(question):
    if question["family"] in MEMORY_FAMILIES:
        return memory.response_payload(
            question
        )

    return public_question(question)


def evaluate_response(
    question,
    selected_option_id,
):
    validate_question(question)

    result = score_response(
        question,
        selected_option_id,
    )

    result["domain"] = question["domain"]
    result["family"] = question["family"]
    result["difficulty"] = question["difficulty"]

    result["registry_version"] = (
        REGISTRY_VERSION
    )

    result["calibration_status"] = (
        "uncalibrated"
    )

    return result


def run_tests():
    registry = get_registry()

    assert registry["family_count"] == 18
    assert len(registry["domains"]) == 6

    assert all(
        len(families) == 3
        for families in registry["domains"].values()
    )

    print("Complete family registration: PASSED")

    total = 0

    private_fields = {
        "correct_option_id",
        "explanation",
        "seed",
        "content_hash",
        "prompt_hash",
        "exposure_hash",
    }

    for family in sorted(GENERATORS):
        for difficulty in range(1, 6):
            for index in range(100):
                seed = f"registry-test-{index}"

                question = generate_question(
                    family,
                    difficulty,
                    seed=seed,
                )

                assert question == generate_question(
                    family,
                    difficulty,
                    seed=seed,
                )

                assert question["family"] == family

                presentation = presentation_question(
                    question
                )

                response = response_question(
                    question
                )

                assert not (
                    private_fields & set(presentation)
                )

                assert not (
                    private_fields & set(response)
                )

                if family in MEMORY_FAMILIES:
                    assert "memorize" in presentation
                    assert "options" not in presentation
                    assert "memorize" not in response
                    assert "stimulus" not in response

                correct = evaluate_response(
                    question,
                    question["correct_option_id"],
                )

                assert correct["correct"] is True

                incorrect_id = next(
                    option["id"]
                    for option in question["options"]
                    if option["id"] !=
                    question["correct_option_id"]
                )

                incorrect = evaluate_response(
                    question,
                    incorrect_id,
                )

                assert incorrect["correct"] is False

                total += 1

        print(
            f"{family}: "
            "500 integration cases PASSED"
        )

    assert total == 9000

    original = generate_question(
        "number_sequences",
        3,
        seed="exposure-test",
    )

    replacement = generate_question(
        "number_sequences",
        3,
        seed="exposure-test",
        excluded_exposures={
            original["exposure_hash"]
        },
    )

    assert (
        original["exposure_hash"]
        != replacement["exposure_hash"]
    )

    print("Question exposure exclusion: PASSED")

    try:
        generate_question(
            "number_sequences",
            3,
            seed="exposure-test",
            excluded_exposures={
                original["exposure_hash"]
            },
            max_attempts=1,
        )

    except QuestionPoolExhausted:
        print(
            "Bounded exposure search: PASSED"
        )

    else:
        raise AssertionError(
            "Exposure restriction bypassed."
        )

    for family in GENERATORS:
        question = generate_question(
            family,
            3,
            seed="registry-negative-control",
        )

        corrupted = deepcopy(question)

        corrupted["correct_option_id"] = next(
            option["id"]
            for option in corrupted["options"]
            if option["id"] !=
            corrupted["correct_option_id"]
        )

        try:
            validate_question(corrupted)

        except QuestionValidationError:
            pass

        else:
            raise AssertionError(
                f"Invalid answer accepted: {family}"
            )

    print(
        "All 18 corrupted answer-key "
        "controls: PASSED"
    )

    print("Private payload isolation: PASSED")
    print("Working memory stage isolation: PASSED")
    print("Unified response scoring: PASSED")

    print()
    print("ALL 9,000 REGISTRY INTEGRATION TESTS PASSED")


if __name__ == "__main__":
    run_tests()

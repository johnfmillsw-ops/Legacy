
"""
Legacy Phase VII: Theoretical domain ability estimation.

Estimates latent ability under explicitly assumed
item-response parameters and a standard normal prior.

These estimates are not population-normed IQ scores.
"""

from math import isfinite

from cognitive_scoring_parameters import (
    parameters_for_item,
    parameter_model_id,
)

from cognitive_psychometrics import (
    estimate_eap,
)

from cognitive_registry import evaluate_response


DOMAIN_SCORING_VERSION = 2

UNTIMED_DOMAINS = (
    "fluid_reasoning",
    "visual_spatial",
    "verbal_comprehension",
    "quantitative_reasoning",
    "working_memory",
)

EXPECTED_ITEMS_PER_DOMAIN = 12


def score_domain(domain, records, responses):

    if domain not in UNTIMED_DOMAINS:
        raise ValueError(
            "Unsupported untimed cognitive domain."
        )

    records = list(records)
    responses = list(responses)

    if len(records) != EXPECTED_ITEMS_PER_DOMAIN:
        raise ValueError(
            "Incomplete domain item inventory."
        )

    if len(responses) != len(records):
        raise ValueError(
            "Incomplete domain response inventory."
        )

    indexed = {}

    for response in responses:
        item_id = response["item_id"]

        if item_id in indexed:
            raise ValueError(
                "Duplicate item response."
            )

        indexed[item_id] = response

    parameters = []
    binary_responses = []
    seen_items = set()

    for record in records:

        content = record["content"]
        item_id = record["item_id"]

        if content["domain"] != domain:
            raise ValueError(
                "Cross-domain item detected."
            )

        if item_id in seen_items:
            raise ValueError(
                "Duplicate assessment item."
            )

        seen_items.add(item_id)

        if item_id not in indexed:
            raise ValueError(
                "Missing item response."
            )

        response = indexed[item_id]

        if (
            response["presentation_id"]
            != record["presentation_id"]
        ):
            raise ValueError(
                "Presentation identity mismatch."
            )

        question = record["question_snapshot"]

        if response["question_id"] != question["id"]:
            raise ValueError(
                "Question identity mismatch."
            )

        if response["outcome"] not in (
            "correct", "incorrect"
        ):
            raise ValueError(
                "Incomplete untimed administration."
            )

        verified = evaluate_response(
            question,
            response["selected_option_id"],
        )

        correct = verified["correct"]

        if response["correct"] is not correct:
            raise ValueError(
                "Stored answer correctness mismatch."
            )

        expected_outcome = (
            "correct" if correct else "incorrect"
        )

        if response["outcome"] != expected_outcome:
            raise ValueError(
                "Stored response outcome mismatch."
            )

        parameters.append(
            parameters_for_item(record)
        )

        binary_responses.append(
            int(correct)
        )

    if set(indexed) != seen_items:
        raise ValueError(
            "Unexpected response identities."
        )

    estimate = estimate_eap(
        parameters,
        binary_responses,
    )

    correct_count = sum(binary_responses)

    return {
        "domain": domain,
        "scoring_version": DOMAIN_SCORING_VERSION,
        "parameter_model_id": parameter_model_id(),
        "item_count": len(records),
        "correct_count": correct_count,
        "incorrect_count":
            len(records) - correct_count,
        "raw_accuracy":
            correct_count / len(records),
        "ability_estimate": estimate,
        "parameter_source":
            "theoretical_assumptions",
        "population_normed": False,
        "scientifically_validated": False,
        "measurement_status":
            "theoretical_model_estimate",
    }


def score_untimed_domains(session):

    if session.state != "completed":
        raise ValueError(
            "Assessment must be completed."
        )

    results = {}

    for domain in UNTIMED_DOMAINS:

        records = [
            record
            for block in session.blocks
            if block["domain"] == domain
            for record in block["items"]
        ]

        responses = [
            response
            for response in session.responses
            if response["domain"] == domain
        ]

        results[domain] = score_domain(
            domain,
            records,
            responses,
        )

    return results


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

    bank = build_research_bank()

    form = assemble_assessment(
        bank,
        "domain-scoring-verification-v1",
    )

    session = AssessmentSession(
        form,
        bank,
        1000,
    )

    try:
        score_untimed_domains(session)
    except ValueError:
        print("Incomplete assessment rejection: PASSED")
    else:
        raise AssertionError(
            "Incomplete assessment was scored."
        )

    complete_session(session)

    results = score_untimed_domains(session)

    require(
        set(results) == set(UNTIMED_DOMAINS),
        "Incorrect domain inventory.",
    )

    print("Five cognitive domain estimates: PASSED")

    for domain, result in results.items():

        require(
            result["item_count"] == 12
            and result["correct_count"] == 12,
            "Incorrect domain response totals.",
        )

        require(
            result["population_normed"] is False
            and result["scientifically_validated"]
            is False,
            "Unsupported scientific claim.",
        )

        print(
            domain,
            result["ability_estimate"],
        )

    print("60 untimed response outcomes: PASSED")

    domain = "fluid_reasoning"

    records = [
        record
        for block in session.blocks
        if block["domain"] == domain
        for record in block["items"]
    ]

    responses = [
        response
        for response in session.responses
        if response["domain"] == domain
    ]

    original = score_domain(
        domain, records, responses
    )

    reversed_result = score_domain(
        domain,
        list(reversed(records)),
        list(reversed(responses)),
    )

    require(
        original["correct_count"]
        == reversed_result["correct_count"],
        "Response order changed scoring totals.",
    )

    print("Response identity matching: PASSED")

    def expect_rejection(
        test_records,
        test_responses,
        label,
    ):
        try:
            score_domain(
                domain,
                test_records,
                test_responses,
            )
        except ValueError:
            print(label + ": PASSED")
        else:
            raise AssertionError(
                "Invalid data accepted: " + label
            )

    expect_rejection(
        records,
        responses[:-1],
        "Missing response rejection",
    )

    duplicate = deepcopy(responses)
    duplicate[-1] = deepcopy(duplicate[0])

    expect_rejection(
        records,
        duplicate,
        "Duplicate response rejection",
    )

    corrupted = deepcopy(responses)
    corrupted[0]["correct"] = False

    expect_rejection(
        records,
        corrupted,
        "Corrupted correctness rejection",
    )

    corrupted = deepcopy(responses)
    corrupted[0]["presentation_id"] = "invalid"

    expect_rejection(
        records,
        corrupted,
        "Presentation mismatch rejection",
    )

    corrupted = deepcopy(responses)
    corrupted[0]["question_id"] = "invalid"

    expect_rejection(
        records,
        corrupted,
        "Question mismatch rejection",
    )

    incorrect = deepcopy(responses)

    indexed = {
        record["item_id"]: record
        for record in records
    }

    for response in incorrect:

        record = indexed[response["item_id"]]

        question = record["question_snapshot"]

        wrong = next(
            option["id"]
            for option in question["options"]
            if option["id"]
            != question["correct_option_id"]
        )

        response["selected_option_id"] = wrong
        response["correct"] = False
        response["outcome"] = "incorrect"

    low = score_domain(
        domain,
        records,
        incorrect,
    )

    require(
        low["correct_count"] == 0,
        "Incorrect zero-score accounting.",
    )

    print("Zero-correct response scoring: PASSED")

    print()
    print("All-correct ability estimate:")
    print(original["ability_estimate"])

    print()
    print("All-incorrect ability estimate:")
    print(low["ability_estimate"])

    print()
    print("ALL COGNITIVE DOMAIN TESTS PASSED")


if __name__ == "__main__":
    run_tests()

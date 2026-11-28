
"""
Legacy Phase VII: Processing speed measurement.

Measures observed accuracy, response latency and
guessing-adjusted throughput under fixed time limits.

Does not claim population-relative processing ability.
"""

from math import fsum, isclose
from statistics import median

from cognitive_engine import fingerprint
from cognitive_item_identity import verify_item_record
from cognitive_registry import evaluate_response
from cognitive_timing import speed_block_duration


SPEED_SCORING_VERSION = 1

SPEED_FAMILIES = (
    "symbol_comparison",
    "visual_discrimination",
    "pattern_matching",
)


def scoring_manifest():
    return {
        "version": SPEED_SCORING_VERSION,
        "method": "guessing_adjusted_throughput",
        "time_unit": "minutes",
        "correct_response_credit": 1.0,
        "incorrect_response_credit":
            "negative_inverse_option_count_minus_one",
        "unanswered_response_credit": 0.0,
        "population_normed": False,
        "scientifically_validated": False,
    }


def score_speed_block(block, responses, block_result):

    if block["domain"] != "processing_speed":
        raise ValueError("Invalid processing domain.")

    family = block["family"]

    if family not in SPEED_FAMILIES:
        raise ValueError("Invalid processing family.")

    if block["mode"] != "timed_queue":
        raise ValueError("Invalid administration mode.")

    duration = speed_block_duration(family)

    if block["duration_ms"] != duration:
        raise ValueError("Invalid block duration.")

    records = block["items"]
    responses = list(responses)

    if (
        len(records) != block["item_count"]
        or len(responses) != len(records)
    ):
        raise ValueError("Incomplete speed inventory.")

    if (
        block_result["domain"] != "processing_speed"
        or block_result["family"] != family
    ):
        raise ValueError("Block result identity mismatch.")

    started = block_result["started_ms"]
    deadline = block_result["deadline_ms"]
    closed = block_result["closed_ms"]

    if (
        deadline != started + duration
        or closed < started
    ):
        raise ValueError("Invalid block timing.")

    indexed = {}

    for response in responses:
        item_id = response["item_id"]

        if item_id in indexed:
            raise ValueError("Duplicate speed response.")

        indexed[item_id] = response

    counts = {
        "correct": 0,
        "incorrect": 0,
        "timed_out": 0,
        "not_reached": 0,
    }

    credits = []
    latencies = []
    seen = set()

    for record in records:

        verify_item_record(record)

        item_id = record["item_id"]

        if item_id in seen:
            raise ValueError("Duplicate speed item.")

        seen.add(item_id)

        if item_id not in indexed:
            raise ValueError("Missing speed response.")

        response = indexed[item_id]
        question = record["question_snapshot"]

        if (
            question["family"] != family
            or question["domain"] != "processing_speed"
            or response["presentation_id"]
                != record["presentation_id"]
            or response["question_id"] != question["id"]
        ):
            raise ValueError("Speed identity mismatch.")

        outcome = response["outcome"]

        if outcome not in counts:
            raise ValueError("Invalid response outcome.")

        counts[outcome] += 1

        if outcome in ("correct", "incorrect"):

            verified = evaluate_response(
                question,
                response["selected_option_id"],
            )

            correct = verified["correct"]

            if (
                response["correct"] is not correct
                or correct != (outcome == "correct")
            ):
                raise ValueError("Incorrect scoring record.")

            presented = response["presented_ms"]
            response_started = response["response_started_ms"]
            recorded = response["recorded_ms"]
            latency = response["response_latency_ms"]

            if not all(
                type(value) is int
                for value in (
                    presented,
                    response_started,
                    recorded,
                    latency,
                )
            ):
                raise ValueError("Invalid response timing.")

            if not (
                started <= presented
                <= response_started
                <= recorded
                < deadline
            ):
                raise ValueError("Response outside time limit.")

            if latency != recorded - response_started:
                raise ValueError("Response latency mismatch.")

            latencies.append(latency)

            option_count = len(question["options"])

            credits.append(
                1.0 if correct
                else -1.0 / (option_count - 1)
            )

        else:

            if (
                response["correct"] is not None
                or response["selected_option_id"] is not None
                or response["response_latency_ms"] is not None
            ):
                raise ValueError("Invalid unanswered record.")

            credits.append(0.0)

    if set(indexed) != seen:
        raise ValueError("Unexpected response identities.")

    answered = counts["correct"] + counts["incorrect"]

    minutes = duration / 60000

    adjusted_correct = fsum(credits)

    ceiling_limited = (
        bool(block_result["ceiling_limited"])
        or (
            answered == len(records)
            and closed < deadline
        )
    )

    return {
        "family": family,
        "item_count": len(records),
        "answered": answered,
        **counts,
        "duration_ms": duration,
        "observed_elapsed_ms":
            min(closed - started, duration),
        "accuracy":
            counts["correct"] / answered
            if answered else None,
        "correct_per_minute":
            counts["correct"] / minutes,
        "attempts_per_minute":
            answered / minutes,
        "guessing_adjusted_correct":
            adjusted_correct,
        "adjusted_correct_per_minute":
            adjusted_correct / minutes,
        "median_response_latency_ms":
            median(latencies) if latencies else None,
        "ceiling_limited": ceiling_limited,
        "population_normed": False,
    }


def score_processing_speed(session):

    if session.state != "completed":
        raise ValueError("Assessment must be completed.")

    results = {}

    for index, block in enumerate(session.blocks):

        if block["domain"] != "processing_speed":
            continue

        family = block["family"]

        if family in results:
            raise ValueError("Duplicate processing block.")

        responses = [
            response
            for response in session.responses
            if response["block_index"] == index
        ]

        results[family] = score_speed_block(
            block,
            responses,
            session.block_results[index],
        )

    if set(results) != set(SPEED_FAMILIES):
        raise ValueError("Incomplete processing assessment.")

    totals = {
        key: sum(
            result[key]
            for result in results.values()
        )
        for key in (
            "item_count",
            "answered",
            "correct",
            "incorrect",
            "timed_out",
            "not_reached",
            "duration_ms",
        )
    }

    minutes = totals["duration_ms"] / 60000

    adjusted = fsum(
        result["guessing_adjusted_correct"]
        for result in results.values()
    )

    return {
        "domain": "processing_speed",
        "scoring_version": SPEED_SCORING_VERSION,
        "scoring_model_id":
            fingerprint(scoring_manifest()),
        "families": results,
        **totals,
        "accuracy":
            totals["correct"] / totals["answered"]
            if totals["answered"] else None,
        "correct_per_minute":
            totals["correct"] / minutes,
        "attempts_per_minute":
            totals["answered"] / minutes,
        "guessing_adjusted_correct": adjusted,
        "adjusted_correct_per_minute":
            adjusted / minutes,
        "ceiling_limited": any(
            result["ceiling_limited"]
            for result in results.values()
        ),
        "population_normed": False,
        "scientifically_validated": False,
        "measurement_status": "observed_performance",
    }


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
        "processing-speed-scoring-v1",
    )

    session = AssessmentSession(form, bank, 1000)

    try:
        score_processing_speed(session)
    except ValueError:
        print("Incomplete assessment rejection: PASSED")
    else:
        raise AssertionError("Incomplete session accepted.")

    complete_session(session)

    result = score_processing_speed(session)

    require(
        len(result["families"]) == 3,
        "Incorrect speed family inventory.",
    )

    print("Three processing speed families: PASSED")

    require(
        result["item_count"] == 75
        and result["correct"] == 3
        and result["incorrect"] == 0
        and result["timed_out"] == 3
        and result["not_reached"] == 69,
        "Incorrect speed outcome accounting.",
    )

    print("75 speed response outcomes: PASSED")

    require(
        result["duration_ms"] == 360000,
        "Incorrect speed duration.",
    )

    print("Six-minute administration duration: PASSED")

    require(
        isclose(result["correct_per_minute"], 0.5)
        and isclose(result["adjusted_correct_per_minute"], 0.5)
        and isclose(result["accuracy"], 1.0),
        "Incorrect throughput calculation.",
    )

    print("Correct throughput calculation: PASSED")

    index = next(
        index
        for index, block in enumerate(session.blocks)
        if block["domain"] == "processing_speed"
    )

    block = session.blocks[index]

    block_result = session.block_results[index]

    responses = [
        response
        for response in session.responses
        if response["block_index"] == index
    ]

    def expect_rejection(data, label):
        try:
            score_speed_block(
                block, data, block_result
            )
        except ValueError:
            print(label + ": PASSED")
        else:
            raise AssertionError(
                "Invalid speed data accepted: " + label
            )

    expect_rejection(
        responses[:-1],
        "Missing response rejection",
    )

    duplicate = deepcopy(responses)
    duplicate[-1] = deepcopy(duplicate[0])

    expect_rejection(
        duplicate,
        "Duplicate response rejection",
    )

    corrupted = deepcopy(responses)

    answered = next(
        response for response in corrupted
        if response["outcome"] == "correct"
    )

    answered["recorded_ms"] = block_result["deadline_ms"]

    expect_rejection(
        corrupted,
        "Late response rejection",
    )

    corrupted = deepcopy(responses)

    answered = next(
        response for response in corrupted
        if response["outcome"] == "correct"
    )

    answered["response_latency_ms"] += 1

    expect_rejection(
        corrupted,
        "Latency integrity enforcement",
    )

    incorrect = deepcopy(responses)

    answered = next(
        response for response in incorrect
        if response["outcome"] == "correct"
    )

    record = next(
        record for record in block["items"]
        if record["item_id"] == answered["item_id"]
    )

    question = record["question_snapshot"]

    answered["selected_option_id"] = next(
        option["id"]
        for option in question["options"]
        if option["id"] != question["correct_option_id"]
    )

    answered["correct"] = False
    answered["outcome"] = "incorrect"

    wrong_result = score_speed_block(
        block,
        incorrect,
        block_result,
    )

    expected = -1.0 / (
        len(question["options"]) - 1
    )

    require(
        isclose(
            wrong_result["guessing_adjusted_correct"],
            expected,
        ),
        "Incorrect guessing adjustment.",
    )

    print("Guessing-adjusted scoring: PASSED")

    require(
        result["population_normed"] is False
        and result["scientifically_validated"] is False,
        "Unsupported scientific qualification.",
    )

    print("Scientific reporting safeguards: PASSED")

    print()
    print("Correct per minute:", result["correct_per_minute"])
    print("Accuracy:", result["accuracy"])
    print("Adjusted throughput:", result["adjusted_correct_per_minute"])
    print()
    print("ALL PROCESSING SPEED TESTS PASSED")


if __name__ == "__main__":
    run_tests()

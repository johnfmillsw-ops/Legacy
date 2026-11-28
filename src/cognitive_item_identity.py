
"""
Legacy Phase VII: Research item identity.

Binds exact assessment content, scoring and
administration conditions to a stable identity.

Generated items remain experimental until
independently reviewed and empirically validated.
"""

from copy import deepcopy

from cognitive_engine import fingerprint
from cognitive_registry import (
    generate_question,
    validate_question,
)
from cognitive_timing import (
    get_timing_protocol,
)

ITEM_IDENTITY_VERSION = 1


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def build_item_record(question):
    validate_question(question)

    protocol = get_timing_protocol()

    options = deepcopy(question["options"])

    correct_id = question["correct_option_id"]

    correct_values = [
        option["value"]
        for option in options
        if option["id"] == correct_id
    ]

    if len(correct_values) != 1:
        raise ValueError(
            "Invalid correct answer identity."
        )

    # Answer ordering is deliberately excluded
    # from the underlying research item identity.
    # Exact presentation order is retained separately.
    content = {
        "identity_version": ITEM_IDENTITY_VERSION,
        "framework_version":
            question["framework_version"],
        "engine_version":
            question["engine_version"],
        "family_version":
            question["family_version"],
        "registry_version":
            question["registry_version"],
        "domain": question["domain"],
        "family": question["family"],
        "programmed_difficulty":
            question["difficulty"],
        "prompt": question["prompt"],
        "stimulus": deepcopy(
            question["stimulus"]
        ),
        "answer_values": sorted(
            option["value"]
            for option in options
        ),
        "correct_value": correct_values[0],
        "scoring_rule": "dichotomous_v1",
        "administration_protocol": protocol,
    }

    item_id = fingerprint(content)

    presentation = {
        "item_id": item_id,
        "options": options,
        "correct_option_id": correct_id,
    }

    return {
        "item_id": item_id,
        "presentation_id":
            fingerprint(presentation),
        "identity_version":
            ITEM_IDENTITY_VERSION,
        "content": content,
        "presentation": presentation,
        "question_snapshot":
            deepcopy(question),
        "qualification_status": "experimental",
        "calibration": None,
        "validated_assessment_eligible": False,
        "iq_reporting_enabled": False,
    }


def verify_item_record(record):
    if not isinstance(record, dict):
        raise ValueError(
            "Invalid item record."
        )

    rebuilt = build_item_record(
        record["question_snapshot"]
    )

    immutable_fields = (
        "item_id",
        "presentation_id",
        "identity_version",
        "content",
        "presentation",
    )

    for field in immutable_fields:
        if fingerprint(record.get(field)) != fingerprint(rebuilt[field]):
            raise ValueError(
                f"Item integrity mismatch: {field}"
            )

    if record.get(
        "qualification_status"
    ) != "experimental":
        raise PermissionError(
            "Unauthorized qualification status."
        )

    if record.get("calibration") is not None:
        raise PermissionError(
            "Calibration attachment is not "
            "authorized by this module."
        )

    if record.get(
        "validated_assessment_eligible"
    ) is not False:
        raise PermissionError(
            "Unauthorized assessment eligibility."
        )

    if record.get(
        "iq_reporting_enabled"
    ) is not False:
        raise PermissionError(
            "Unauthorized IQ reporting."
        )

    return True


def research_item_metadata(record):
    verify_item_record(record)

    content = record["content"]

    return {
        "item_id": record["item_id"],
        "presentation_id":
            record["presentation_id"],
        "domain": content["domain"],
        "family": content["family"],
        "programmed_difficulty":
            content["programmed_difficulty"],
        "identity_version":
            record["identity_version"],
        "timing_version":
            content[
                "administration_protocol"
            ]["timing_version"],
        "qualification_status": "experimental",
        "empirically_calibrated": False,
        "iq_reporting_enabled": False,
    }


def require_calibration_identity(
    record,
    calibration_item_id,
):
    verify_item_record(record)

    if calibration_item_id != record["item_id"]:
        raise ValueError(
            "Calibration belongs to a "
            "different assessment item."
        )

    # Matching identity is necessary but
    # not sufficient for scientific approval.
    return True


def run_tests():
    from cognitive_registry import GENERATORS

    total = 0

    for family in sorted(GENERATORS):
        for difficulty in range(1, 6):
            for index in range(20):
                seed = (
                    f"identity-{family}-"
                    f"{difficulty}-{index}"
                )

                question = generate_question(
                    family,
                    difficulty,
                    seed=seed,
                )

                first = build_item_record(
                    question
                )

                second = build_item_record(
                    generate_question(
                        family,
                        difficulty,
                        seed=seed,
                    )
                )

                require(
                    first == second,
                    "Item identity not reproducible.",
                )

                require(
                    verify_item_record(first),
                    "Item verification failed.",
                )

                require(
                    require_calibration_identity(
                        first,
                        first["item_id"],
                    ),
                    "Matching identity rejected.",
                )

                metadata = research_item_metadata(
                    first
                )

                require(
                    "correct_value" not in metadata
                    and "question_snapshot"
                    not in metadata
                    and "presentation"
                    not in metadata,
                    "Private answer data exposed.",
                )

                total += 1

    print(
        f"{total:,} item identity "
        "verification cases: PASSED"
    )

    question = generate_question(
        "number_sequences",
        3,
        seed="identity-control",
    )

    original = build_item_record(question)

    reordered = deepcopy(question)

    reordered["options"].reverse()

    changed_order = build_item_record(
        reordered
    )

    require(
        original["item_id"]
        == changed_order["item_id"],
        "Answer ordering changed item identity.",
    )

    require(
        original["presentation_id"]
        != changed_order["presentation_id"],
        "Presentation change not detected.",
    )

    print("Answer-order identity separation: PASSED")

    modified = deepcopy(original)

    modified["content"][
        "administration_protocol"
    ]["timing_version"] += 1

    require(
        fingerprint(modified["content"])
        != original["item_id"],
        "Timing protocol change not detected.",
    )

    print("Timing protocol identity binding: PASSED")

    modified = deepcopy(original)

    modified["content"]["correct_value"] = (
        "invalid-answer"
    )

    require(
        fingerprint(modified["content"])
        != original["item_id"],
        "Scoring rule change not detected.",
    )

    print("Answer-key identity binding: PASSED")

    invalid_records = []

    for field, value in (
        ("item_id", "invalid"),
        ("presentation_id", "invalid"),
        ("qualification_status", "validated"),
        ("calibration", {"difficulty": 0}),
        ("validated_assessment_eligible", True),
        ("iq_reporting_enabled", True),
    ):
        modified = deepcopy(original)
        modified[field] = value
        invalid_records.append(modified)

    modified = deepcopy(original)
    modified["content"]["prompt"] += " Modified."
    invalid_records.append(modified)

    modified = deepcopy(original)

    modified["content"][
        "administration_protocol"
    ]["timing_version"] += 1

    invalid_records.append(modified)

    for record in invalid_records:
        try:
            verify_item_record(record)
        except (ValueError, PermissionError):
            pass
        else:
            raise AssertionError(
                "Modified item record accepted."
            )

    print("8 integrity negative controls: PASSED")

    try:
        require_calibration_identity(
            original,
            "different-item-id",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Unrelated calibration accepted."
        )

    print("Calibration identity isolation: PASSED")

    snapshot = deepcopy(original)

    question["options"].clear()

    require(
        original == snapshot,
        "Original question mutation affected record.",
    )

    print("Question snapshot isolation: PASSED")

    require(
        original["calibration"] is None
        and not original[
            "validated_assessment_eligible"
        ]
        and not original["iq_reporting_enabled"],
        "Scientific reporting safeguards failed.",
    )

    print("Scientific reporting safeguards: PASSED")

    print()
    print("ALL ITEM IDENTITY TESTS PASSED")


if __name__ == "__main__":
    run_tests()

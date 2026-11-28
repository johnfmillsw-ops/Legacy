
"""
Legacy Phase VII: Experimental research item bank.

Deterministic, versioned research item recruitment.
Separates stable assessment items from procedural
practice questions.

No generated item is automatically calibrated
or scientifically validated.
"""

from copy import deepcopy
from collections import Counter

from cognitive_engine import fingerprint

from cognitive_registry import (
    GENERATORS,
    generate_question,
)

from cognitive_item_identity import (
    build_item_record,
    verify_item_record,
)

BANK_VERSION = 1

DEFAULT_ITEMS_PER_LEVEL = 5

MAX_ATTEMPTS_PER_LEVEL = 1000


def build_research_bank(
    items_per_level=DEFAULT_ITEMS_PER_LEVEL,
    bank_seed="legacy-research-pilot-v1",
):
    if not __debug__:
        raise RuntimeError(
            "Question verification requires "
            "Python assertions to be enabled."
        )

    if (
        type(items_per_level) is not int
        or not 1 <= items_per_level <= 5
    ):
        raise ValueError(
            "Items per level must be 1 through 5."
        )

    if (
        not isinstance(bank_seed, str)
        or not bank_seed.strip()
        or len(bank_seed) > 128
    ):
        raise ValueError("Invalid bank seed.")

    records = []
    item_ids = set()
    exposures = set()

    for family in sorted(GENERATORS):
        for difficulty in range(1, 6):
            recruited = 0

            for attempt in range(
                MAX_ATTEMPTS_PER_LEVEL
            ):
                seed = fingerprint({
                    "bank_version": BANK_VERSION,
                    "bank_seed": bank_seed,
                    "family": family,
                    "difficulty": difficulty,
                    "attempt": attempt,
                })

                question = generate_question(
                    family,
                    difficulty,
                    seed=seed,
                )

                exposure = question[
                    "exposure_hash"
                ]

                if exposure in exposures:
                    continue

                record = build_item_record(
                    question
                )

                item_id = record["item_id"]

                if item_id in item_ids:
                    continue

                verify_item_record(record)

                records.append(record)

                item_ids.add(item_id)
                exposures.add(exposure)

                recruited += 1

                if recruited == items_per_level:
                    break

            if recruited != items_per_level:
                raise RuntimeError(
                    "Unable to recruit sufficient "
                    "distinct research items: "
                    f"{family}, level {difficulty}."
                )

    manifest = {
        "bank_version": BANK_VERSION,
        "bank_seed": bank_seed,
        "items_per_level": items_per_level,
        "item_ids": [
            record["item_id"]
            for record in records
        ],
        "presentation_ids": [
            record["presentation_id"]
            for record in records
        ],
    }

    return {
        "bank_id": fingerprint(manifest),
        "manifest": manifest,
        "records": records,
        "item_count": len(records),
        "qualification_status": "experimental",
        "content_reviewed": False,
        "empirically_calibrated": False,
        "validated_assessment_eligible": False,
        "iq_reporting_enabled": False,
    }


def verify_research_bank(bank):
    manifest = bank["manifest"]
    records = bank["records"]

    if manifest["bank_version"] != BANK_VERSION:
        raise ValueError(
            "Unsupported bank version."
        )

    if bank["bank_id"] != fingerprint(manifest):
        raise ValueError(
            "Bank manifest integrity mismatch."
        )

    if bank["item_count"] != len(records):
        raise ValueError(
            "Bank item count mismatch."
        )

    if bank.get(
        "qualification_status"
    ) != "experimental":
        raise PermissionError(
            "Unauthorized bank qualification."
        )

    for field in (
        "content_reviewed",
        "empirically_calibrated",
        "validated_assessment_eligible",
        "iq_reporting_enabled",
    ):
        if bank.get(field) is not False:
            raise PermissionError(
                f"Unauthorized bank status: {field}"
            )

    item_ids = []
    presentation_ids = []
    exposures = set()
    coverage = Counter()

    for record in records:
        verify_item_record(record)

        item_ids.append(record["item_id"])

        presentation_ids.append(
            record["presentation_id"]
        )

        question = record["question_snapshot"]

        exposure = question["exposure_hash"]

        if exposure in exposures:
            raise ValueError(
                "Duplicate item exposure."
            )

        exposures.add(exposure)

        content = record["content"]

        coverage[(
            content["family"],
            content["programmed_difficulty"],
        )] += 1

    if len(set(item_ids)) != len(item_ids):
        raise ValueError(
            "Duplicate research item identity."
        )

    if item_ids != manifest["item_ids"]:
        raise ValueError(
            "Research item manifest mismatch."
        )

    if presentation_ids != (
        manifest["presentation_ids"]
    ):
        raise ValueError(
            "Presentation manifest mismatch."
        )

    count = manifest["items_per_level"]

    if type(count) is not int or not 1 <= count <= 5:
        raise ValueError(
            "Invalid bank recruitment count."
        )

    expected = {
        (family, difficulty): count
        for family in GENERATORS
        for difficulty in range(1, 6)
    }

    if dict(coverage) != expected:
        raise ValueError(
            "Research bank coverage mismatch."
        )

    return True


def summarize_bank(bank):
    verify_research_bank(bank)

    domains = Counter()
    families = Counter()
    difficulties = Counter()

    for record in bank["records"]:
        content = record["content"]

        domains[content["domain"]] += 1
        families[content["family"]] += 1

        difficulties[
            content["programmed_difficulty"]
        ] += 1

    return {
        "bank_id": bank["bank_id"],
        "item_count": bank["item_count"],
        "domains": dict(domains),
        "families": dict(families),
        "difficulty_distribution":
            dict(difficulties),
        "qualification_status": "experimental",
        "iq_reporting_enabled": False,
    }


def get_research_item(bank, item_id):
    verify_research_bank(bank)

    for record in bank["records"]:
        if record["item_id"] == item_id:
            return deepcopy(record)

    raise KeyError(
        "Research item does not exist."
    )


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_tests():
    bank = build_research_bank()

    require(
        verify_research_bank(bank),
        "Research bank verification failed.",
    )

    require(
        bank["item_count"] == 450,
        "Incorrect research bank size.",
    )

    print("450-item research bank: PASSED")

    summary = summarize_bank(bank)

    require(
        len(summary["domains"]) == 6
        and all(
            count == 75
            for count in summary[
                "domains"
            ].values()
        ),
        "Incorrect domain coverage.",
    )

    print("Six-domain coverage: PASSED")

    require(
        len(summary["families"]) == 18
        and all(
            count == 25
            for count in summary[
                "families"
            ].values()
        ),
        "Incorrect family coverage.",
    )

    print("18-family coverage: PASSED")

    require(
        summary["difficulty_distribution"]
        == {
            level: 90
            for level in range(1, 6)
        },
        "Incorrect difficulty distribution.",
    )

    print("Five-level difficulty coverage: PASSED")

    rebuilt = build_research_bank()

    require(
        rebuilt == bank,
        "Research bank is not reproducible.",
    )

    print("Deterministic bank reconstruction: PASSED")

    alternate = build_research_bank(
        bank_seed="legacy-alternate-pilot-v1"
    )

    require(
        alternate["bank_id"] != bank["bank_id"],
        "Alternate bank identity collision.",
    )

    print("Alternate bank identity: PASSED")

    first_id = bank["records"][0]["item_id"]

    item = get_research_item(
        bank, first_id
    )

    item["content"]["prompt"] = "Modified."

    require(
        item != bank["records"][0],
        "Retrieved item mutated original bank.",
    )

    print("Item retrieval isolation: PASSED")

    invalid_banks = []

    modified = deepcopy(bank)
    modified["bank_id"] = "invalid"
    invalid_banks.append(modified)

    modified = deepcopy(bank)
    modified["records"].pop()
    invalid_banks.append(modified)

    modified = deepcopy(bank)
    modified["records"][0]["content"][
        "prompt"
    ] = "Modified."
    invalid_banks.append(modified)

    modified = deepcopy(bank)
    modified["records"][1] = deepcopy(
        modified["records"][0]
    )
    invalid_banks.append(modified)

    modified = deepcopy(bank)
    modified["empirically_calibrated"] = True
    invalid_banks.append(modified)

    modified = deepcopy(bank)
    modified["iq_reporting_enabled"] = True
    invalid_banks.append(modified)

    for modified in invalid_banks:
        try:
            verify_research_bank(modified)
        except (ValueError, PermissionError):
            pass
        else:
            raise AssertionError(
                "Invalid research bank accepted."
            )

    print("6 bank integrity controls: PASSED")

    for invalid_count in (
        0, -1, 6, True, 2.5
    ):
        try:
            build_research_bank(
                items_per_level=invalid_count
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Invalid recruitment count accepted."
            )

    print("5 invalid recruitment controls: PASSED")

    require(
        not bank["content_reviewed"]
        and not bank["empirically_calibrated"]
        and not bank[
            "validated_assessment_eligible"
        ]
        and not bank["iq_reporting_enabled"],
        "Scientific reporting safeguards failed.",
    )

    print("Scientific reporting safeguards: PASSED")

    print()
    print("Research bank distribution:")

    for domain, count in sorted(
        summary["domains"].items()
    ):
        print(f"  {domain}: {count}")

    print()
    print("Bank ID:", bank["bank_id"])

    print()
    print("ALL RESEARCH BANK TESTS PASSED")


if __name__ == "__main__":
    run_tests()

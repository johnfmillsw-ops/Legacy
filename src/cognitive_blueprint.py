
"""
Legacy Phase VII: Experimental assessment forms.

Reproducible research assessment assembly,
balanced family coverage, exposure exclusion
and versioned administration protocols.

Not a validated intelligence instrument.
"""

from copy import deepcopy
from collections import Counter
from random import Random

from cognitive_engine import fingerprint

from cognitive_research_bank import (
    build_research_bank,
    verify_research_bank,
)

from cognitive_timing import (
    get_timing_protocol,
    speed_block_duration,
)

BLUEPRINT_VERSION = 1

DOMAIN_ORDER = (
    "fluid_reasoning",
    "visual_spatial",
    "verbal_comprehension",
    "quantitative_reasoning",
    "working_memory",
    "processing_speed",
)

FIXED_ITEMS_PER_FAMILY = 4

DIFFICULTY_PROFILES = (
    (1, 2, 3, 4),
    (1, 2, 4, 5),
    (2, 3, 4, 5),
)


class AssessmentAssemblyError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def assemble_assessment(
    bank,
    form_seed,
    excluded_exposures=(),
):
    verify_research_bank(bank)

    if (
        not isinstance(form_seed, str)
        or not form_seed.strip()
        or len(form_seed) > 128
    ):
        raise ValueError("Invalid form seed.")

    exclusions = set(excluded_exposures)

    if any(
        not isinstance(value, str)
        or not value
        for value in exclusions
    ):
        raise ValueError(
            "Invalid exposure exclusion."
        )

    rng = Random(
        int(
            fingerprint({
                "blueprint_version":
                    BLUEPRINT_VERSION,
                "bank_id": bank["bank_id"],
                "form_seed": form_seed,
            }),
            16,
        )
    )

    pools = {}

    for record in bank["records"]:
        content = record["content"]

        exposure = record[
            "question_snapshot"
        ]["exposure_hash"]

        if exposure in exclusions:
            continue

        key = (
            content["domain"],
            content["family"],
            content["programmed_difficulty"],
        )

        pools.setdefault(key, []).append(
            record
        )

    protocol = get_timing_protocol()

    sections = []

    selected_ids = set()
    selected_exposures = set()

    for domain in DOMAIN_ORDER:
        families = sorted({
            record["content"]["family"]
            for record in bank["records"]
            if record["content"]["domain"]
            == domain
        })

        if len(families) != 3:
            raise AssessmentAssemblyError(
                "Unexpected domain family coverage."
            )

        section = {
            "domain": domain,
            "timing_mode": protocol[
                "domains"
            ][domain]["timing_mode"],
            "budget_ms": protocol[
                "domains"
            ][domain]["budget_ms"],
            "blocks": [],
        }

        profiles = list(DIFFICULTY_PROFILES)

        rng.shuffle(profiles)

        for family_index, family in enumerate(
            families
        ):
            selected = []

            if domain == "processing_speed":
                # Finite research queue.
                # Actual attempted count depends
                # on the timed session.
                for difficulty in range(1, 6):
                    candidates = list(
                        pools.get(
                            (domain, family, difficulty),
                            [],
                        )
                    )

                    if not candidates:
                        raise AssessmentAssemblyError(
                            "Missing speed items: "
                            f"{family}, {difficulty}"
                        )

                    rng.shuffle(candidates)

                    selected.extend(candidates)

                rng.shuffle(selected)

                block = {
                    "family": family,
                    "mode": "timed_queue",
                    "duration_ms":
                        speed_block_duration(family),
                    "items": [],
                }

            else:
                for difficulty in profiles[
                    family_index
                ]:
                    candidates = pools.get(
                        (domain, family, difficulty),
                        [],
                    )

                    if not candidates:
                        raise AssessmentAssemblyError(
                            "Insufficient unexposed items: "
                            f"{family}, {difficulty}"
                        )

                    selected.append(
                        rng.choice(candidates)
                    )

                block = {
                    "family": family,
                    "mode": "fixed_items",
                    "duration_ms": None,
                    "items": [],
                }

            for record in selected:
                item_id = record["item_id"]

                exposure = record[
                    "question_snapshot"
                ]["exposure_hash"]

                if (
                    item_id in selected_ids
                    or exposure in selected_exposures
                    or exposure in exclusions
                ):
                    raise AssessmentAssemblyError(
                        "Duplicate or excluded item."
                    )

                selected_ids.add(item_id)
                selected_exposures.add(exposure)

                block["items"].append(
                    deepcopy(record)
                )

            block["item_count"] = len(
                block["items"]
            )

            section["blocks"].append(block)

        section["item_count"] = sum(
            block["item_count"]
            for block in section["blocks"]
        )

        sections.append(section)

    manifest = {
        "blueprint_version":
            BLUEPRINT_VERSION,
        "bank_id": bank["bank_id"],
        "form_seed": form_seed,
        "administration_protocol": protocol,
        "excluded_exposures": sorted(exclusions),
        "sections": [
            {
                "domain": section["domain"],
                "timing_mode":
                    section["timing_mode"],
                "budget_ms": section["budget_ms"],
                "blocks": [
                    {
                        "family": block["family"],
                        "mode": block["mode"],
                        "duration_ms":
                            block["duration_ms"],
                        "item_ids": [
                            record["item_id"]
                            for record in block["items"]
                        ],
                        "presentation_ids": [
                            record["presentation_id"]
                            for record in block["items"]
                        ],
                    }
                    for block in section["blocks"]
                ],
            }
            for section in sections
        ],
    }

    return {
        "form_id": fingerprint(manifest),
        "manifest": manifest,
        "sections": sections,
        "fixed_item_count": sum(
            section["item_count"]
            for section in sections
            if section["domain"]
            != "processing_speed"
        ),
        "speed_queue_count": sum(
            section["item_count"]
            for section in sections
            if section["domain"]
            == "processing_speed"
        ),
        "qualification_status": "experimental",
        "immediate_feedback": False,
        "adaptive": False,
        "validated_assessment_eligible": False,
        "iq_reporting_enabled": False,
    }


def verify_assessment(form, bank):
    manifest = form["manifest"]

    if form["form_id"] != fingerprint(manifest):
        raise ValueError(
            "Assessment manifest mismatch."
        )

    if manifest["bank_id"] != bank["bank_id"]:
        raise ValueError(
            "Assessment bank mismatch."
        )

    expected = assemble_assessment(
        bank,
        manifest["form_seed"],
        manifest["excluded_exposures"],
    )

    if form != expected:
        raise ValueError(
            "Assessment integrity mismatch."
        )

    return True


def summarize_assessment(form, bank):
    verify_assessment(form, bank)

    return {
        "form_id": form["form_id"],
        "fixed_item_count":
            form["fixed_item_count"],
        "speed_queue_count":
            form["speed_queue_count"],
        "sections": [
            {
                "domain": section["domain"],
                "timing_mode":
                    section["timing_mode"],
                "budget_ms":
                    section["budget_ms"],
                "item_count":
                    section["item_count"],
                "blocks": [
                    {
                        "family": block["family"],
                        "mode": block["mode"],
                        "duration_ms":
                            block["duration_ms"],
                        "item_count":
                            block["item_count"],
                    }
                    for block in section["blocks"]
                ],
            }
            for section in form["sections"]
        ],
        "qualification_status": "experimental",
        "iq_reporting_enabled": False,
    }


def run_tests():
    bank = build_research_bank()

    form = assemble_assessment(
        bank,
        "assessment-pilot-001",
    )

    require(
        verify_assessment(form, bank),
        "Assessment verification failed.",
    )

    require(
        form["fixed_item_count"] == 60,
        "Incorrect fixed item count.",
    )

    require(
        form["speed_queue_count"] == 75,
        "Incorrect speed queue count.",
    )

    print("Assessment assembly: PASSED")

    require(
        tuple(
            section["domain"]
            for section in form["sections"]
        ) == DOMAIN_ORDER,
        "Incorrect domain administration order.",
    )

    print("Standardized domain order: PASSED")

    all_ids = []
    all_exposures = []

    for section in form["sections"]:
        require(
            len(section["blocks"]) == 3,
            "Incorrect family block count.",
        )

        if section["domain"] != "processing_speed":
            require(
                section["item_count"] == 12,
                "Incorrect domain item count.",
            )

            for block in section["blocks"]:
                require(
                    block["item_count"] == 4,
                    "Incorrect family item count.",
                )

                levels = tuple(
                    record["content"][
                        "programmed_difficulty"
                    ]
                    for record in block["items"]
                )

                require(
                    levels in DIFFICULTY_PROFILES,
                    "Invalid difficulty profile.",
                )

        else:
            for block in section["blocks"]:
                require(
                    block["mode"] == "timed_queue"
                    and block["duration_ms"]
                    == 120000
                    and block["item_count"] == 25,
                    "Incorrect speed block.",
                )

        for block in section["blocks"]:
            for record in block["items"]:
                all_ids.append(record["item_id"])

                all_exposures.append(
                    record["question_snapshot"][
                        "exposure_hash"
                    ]
                )

    print("Family and difficulty coverage: PASSED")
    print("Three timed speed blocks: PASSED")

    require(
        len(all_ids) == len(set(all_ids)),
        "Duplicate assessment item.",
    )

    require(
        len(all_exposures)
        == len(set(all_exposures)),
        "Duplicate assessment exposure.",
    )

    print("Within-form exposure uniqueness: PASSED")

    repeated = assemble_assessment(
        bank,
        "assessment-pilot-001",
    )

    require(
        repeated == form,
        "Assessment is not reproducible.",
    )

    print("Deterministic form reconstruction: PASSED")

    alternate = assemble_assessment(
        bank,
        "assessment-pilot-002",
    )

    require(
        alternate["form_id"] != form["form_id"],
        "Alternate form identity collision.",
    )

    print("Alternate form identity: PASSED")

    excluded = {
        form["sections"][0]["blocks"][0][
            "items"
        ][0]["question_snapshot"][
            "exposure_hash"
        ]
    }

    replacement = assemble_assessment(
        bank,
        "assessment-pilot-001",
        excluded_exposures=excluded,
    )

    for section in replacement["sections"]:
        for block in section["blocks"]:
            for record in block["items"]:
                require(
                    record["question_snapshot"][
                        "exposure_hash"
                    ] not in excluded,
                    "Excluded item was selected.",
                )

    print("Previous exposure exclusion: PASSED")

    try:
        assemble_assessment(
            bank,
            "exhausted-form",
            excluded_exposures={
                record["question_snapshot"][
                    "exposure_hash"
                ]
                for record in bank["records"]
            },
        )
    except AssessmentAssemblyError:
        pass
    else:
        raise AssertionError(
            "Exhausted bank accepted."
        )

    print("Insufficient item pool detection: PASSED")

    invalid_forms = []

    modified = deepcopy(form)
    modified["form_id"] = "invalid"
    invalid_forms.append(modified)

    modified = deepcopy(form)
    modified["sections"][0]["blocks"][0][
        "items"
    ].pop()
    invalid_forms.append(modified)

    modified = deepcopy(form)
    modified["iq_reporting_enabled"] = True
    invalid_forms.append(modified)

    modified = deepcopy(form)
    modified["immediate_feedback"] = True
    invalid_forms.append(modified)

    modified = deepcopy(form)
    modified["adaptive"] = True
    invalid_forms.append(modified)

    for modified in invalid_forms:
        try:
            verify_assessment(modified, bank)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Modified assessment accepted."
            )

    print("5 assessment integrity controls: PASSED")

    summary = summarize_assessment(
        form, bank
    )

    for section in summary["sections"]:
        for block in section["blocks"]:
            require(
                "items" not in block,
                "Private item data exposed.",
            )

    print("Public assessment summary isolation: PASSED")

    require(
        not form["adaptive"]
        and not form["immediate_feedback"]
        and not form[
            "validated_assessment_eligible"
        ]
        and not form["iq_reporting_enabled"],
        "Scientific safeguards failed.",
    )

    print("Scientific reporting safeguards: PASSED")

    print()
    print("Assessment distribution:")

    for section in summary["sections"]:
        print(
            f"  {section['domain']}: "
            f"{section['item_count']} available items"
        )

    print()
    print("Fixed questions:", form["fixed_item_count"])
    print("Speed queue:", form["speed_queue_count"])
    print("Form ID:", form["form_id"])

    print()
    print("ALL ASSESSMENT BLUEPRINT TESTS PASSED")


if __name__ == "__main__":
    run_tests()

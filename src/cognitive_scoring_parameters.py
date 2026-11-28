
"""
Legacy Phase VII: Theoretical cognitive scoring parameters.

These parameters establish an explicitly uncalibrated
item-response model. They are not population norms or
empirically estimated item parameters.
"""

from math import isclose

from cognitive_psychometrics import (
    ItemParameters,
    probability_correct,
    item_information,
)

from cognitive_item_identity import (
    verify_item_record,
)

from cognitive_engine import fingerprint


PARAMETER_VERSION = 2

DIFFICULTY_PARAMETERS = {
    1: -2.0,
    2: -1.0,
    3: 0.0,
    4: 1.0,
    5: 2.0,
}

ASSUMED_DISCRIMINATION = 1.0

MODEL_ID = "legacy-theoretical-rasch-v2"


def parameter_manifest():
    return {
        "parameter_version": PARAMETER_VERSION,
        "model_id": MODEL_ID,
        "response_model": "1PL",
        "difficulty_parameters": {
            str(level): value
            for level, value
            in DIFFICULTY_PARAMETERS.items()
        },
        "discrimination": ASSUMED_DISCRIMINATION,
        "guessing_method": "not_explicitly_modeled",
        "parameter_source": "theoretical_assumptions",
        "empirically_calibrated": False,
        "population_normed": False,
        "scientifically_validated": False,
        "processing_speed_method":
            "requires_separate_timed_model",
    }


def parameter_model_id():
    return fingerprint(parameter_manifest())


def parameters_for_item(record):
    verify_item_record(record)

    content = record["content"]

    if content["domain"] == "processing_speed":
        raise ValueError(
            "Timed speed items require a separate "
            "throughput model."
        )

    difficulty = content["programmed_difficulty"]

    if (
        type(difficulty) is not int
        or difficulty not in DIFFICULTY_PARAMETERS
    ):
        raise ValueError(
            "Unsupported programmed difficulty."
        )

    options = record["presentation"]["options"]

    option_count = len(options)

    if not 4 <= option_count <= 6:
        raise ValueError(
            "Unsupported response option count."
        )

    return ItemParameters(
        difficulty=DIFFICULTY_PARAMETERS[difficulty],
        discrimination=ASSUMED_DISCRIMINATION,
        lower_asymptote=0.0,
        model="1PL",
    )


def describe_item_parameters(record):
    parameters = parameters_for_item(record)

    return {
        "item_id": record["item_id"],
        "parameter_model_id": parameter_model_id(),
        "model": parameters.model,
        "difficulty": parameters.difficulty,
        "discrimination":
            parameters.discrimination,
        "lower_asymptote":
            parameters.lower_asymptote,
        "parameter_source":
            "theoretical_assumptions",
        "empirically_calibrated": False,
        "parameter_standard_error": None,
        "population_normed": False,
    }


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_tests():
    from cognitive_research_bank import (
        build_research_bank,
    )

    from copy import deepcopy

    bank = build_research_bank()

    tested = 0
    speed_rejections = 0

    for record in bank["records"]:

        content = record["content"]

        if content["domain"] == "processing_speed":
            try:
                parameters_for_item(record)
            except ValueError:
                speed_rejections += 1
                continue

            raise AssertionError(
                "Speed item accepted by untimed model."
            )

        parameters = parameters_for_item(record)

        level = content["programmed_difficulty"]

        require(
            parameters.difficulty
            == DIFFICULTY_PARAMETERS[level],
            "Incorrect difficulty assignment.",
        )

        option_count = len(
            record["presentation"]["options"]
        )

        require(
            isclose(
                parameters.lower_asymptote,
                0.0,
            ),
            "Incorrect Rasch lower asymptote.",
        )

        probabilities = [
            probability_correct(theta, parameters)
            for theta in (-4, -2, 0, 2, 4)
        ]

        require(
            all(
                a < b
                for a, b in zip(
                    probabilities,
                    probabilities[1:],
                )
            ),
            "Nonmonotonic response probability.",
        )

        require(
            all(
                parameters.lower_asymptote <= p <= 1
                for p in probabilities
            ),
            "Invalid probability range.",
        )

        require(
            item_information(0, parameters) > 0,
            "Invalid item information.",
        )

        metadata = describe_item_parameters(record)

        require(
            metadata["empirically_calibrated"]
            is False
            and metadata["population_normed"]
            is False
            and metadata["parameter_standard_error"]
            is None,
            "Unsupported scientific claim.",
        )

        tested += 1

    require(
        tested == 375,
        f"Incorrect untimed item count: {tested}",
    )

    require(
        speed_rejections == 75,
        "Incorrect speed item count.",
    )

    print("375 untimed item parameter mappings: PASSED")
    print("75 timed item exclusions: PASSED")
    print("Rasch response model: PASSED")
    print("Monotonic response probabilities: PASSED")
    print("Positive item information: PASSED")

    # At equal ability, harder questions must
    # have lower modeled success probabilities.

    parameters = [
        ItemParameters(
            difficulty=DIFFICULTY_PARAMETERS[level],
            discrimination=1.0,
            lower_asymptote=0.0,
            model="1PL",
        )
        for level in range(1, 6)
    ]

    probabilities = [
        probability_correct(0, item)
        for item in parameters
    ]

    require(
        all(
            a > b
            for a, b in zip(
                probabilities,
                probabilities[1:],
            )
        ),
        "Difficulty ordering failed.",
    )

    print("Difficulty ordering: PASSED")

    # Confirm the known midpoint of a
    # three-parameter logistic response curve.

    midpoint = ItemParameters(
        difficulty=0.0,
        discrimination=1.0,
        lower_asymptote=0.0,
        model="1PL",
    )

    require(
        isclose(
            probability_correct(0, midpoint),
            0.5,
            abs_tol=1e-12,
        ),
        "Incorrect analytical midpoint.",
    )

    print("Analytical probability verification: PASSED")

    # Reject corrupted item content.

    record = next(
        record for record in bank["records"]
        if record["content"]["domain"]
        != "processing_speed"
    )

    corrupted = deepcopy(record)

    corrupted["content"][
        "programmed_difficulty"
    ] = 99

    try:
        parameters_for_item(corrupted)
    except (ValueError, RuntimeError, AssertionError):
        print("Corrupted item rejection: PASSED")
    else:
        raise AssertionError(
            "Corrupted item was accepted."
        )

    original_id = parameter_model_id()

    manifest = parameter_manifest()

    manifest["difficulty_parameters"]["1"] = -9.0

    require(
        parameter_model_id() == original_id,
        "Parameter manifest mutation leaked.",
    )

    print("Parameter version isolation: PASSED")

    manifest = parameter_manifest()

    require(
        manifest["empirically_calibrated"] is False
        and manifest["population_normed"] is False
        and manifest["scientifically_validated"] is False,
        "Unsupported qualification.",
    )

    print("Scientific reporting safeguards: PASSED")

    print()
    print("Parameter model:", MODEL_ID)
    print("Parameter fingerprint:", parameter_model_id())
    print()
    print("ALL COGNITIVE PARAMETER TESTS PASSED")


if __name__ == "__main__":
    run_tests()

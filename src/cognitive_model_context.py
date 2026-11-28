from math import isfinite

from cognitive_preferences import selected_result
from cognitive_storage import CognitiveAccessDenied


DOMAIN_LABELS = {
    "fluid_reasoning": "Fluid reasoning",
    "visual_spatial": "Visual-spatial ability",
    "verbal_comprehension": "Verbal comprehension",
    "quantitative_reasoning": "Quantitative reasoning",
    "working_memory": "Working memory",
}


def valid_number(value):

    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not isfinite(number):
        return None

    return number


def build_cognitive_model_context(
    profile,
    profile_id,
    owner_id,
):

    if not profile_id or not owner_id:
        return None

    consent = profile.get("consent", {})

    if not isinstance(consent, dict):
        return None

    if consent.get("has_consent") is not True:
        return None

    if consent.get("allow_remote_processing") is not True:
        return None

    try:
        result = selected_result(
            profile_id,
            owner_id,
            "model",
        )

    except CognitiveAccessDenied:
        return None

    if not result:
        return None

    composite = valid_number(
        result.get("estimated_iq")
    )

    if composite is None:
        return None

    domain_results = result.get(
        "domain_results", {}
    )

    if not isinstance(domain_results, dict):
        return None

    domains = {}

    for key, label in DOMAIN_LABELS.items():

        domain = domain_results.get(key, {})

        score = valid_number(
            domain.get("theoretical_scale_score")
        )

        if score is None:
            continue

        domains[key] = {
            "label": label,
            "theoretical_score": round(score, 2),
            "correct_count": domain.get(
                "correct_count"
            ),
            "item_count": domain.get(
                "item_count"
            ),
        }

    speed = domain_results.get(
        "processing_speed", {}
    )

    return {
        "source": "Legacy cognitive assessment",
        "assessment_id": result["assessment_id"],
        "scoring_version": result.get(
            "scoring_version"
        ),
        "theoretical_iq_scale_score": round(
            composite, 2
        ),
        "domains": domains,
        "processing_speed": {
            "correct_per_minute": valid_number(
                speed.get("correct_per_minute")
            ),
            "accuracy": valid_number(
                speed.get("accuracy")
            ),
            "included_in_composite": False,
        },
        "population_normed": False,
        "scientifically_validated": False,
        "measurement_type": (
            "Experimental cognitive performance"
        ),
    }


def format_cognitive_model_context(context):

    if not context:
        return ""

    lines = [
        "AUTHORIZED COGNITIVE ASSESSMENT",
        "",
        "Source: Legacy experimental cognitive assessment.",
        "",
        "Theoretical IQ-scale estimate: "
        + str(context["theoretical_iq_scale_score"]),
        "",
        "Individual cognitive domains:",
    ]

    for domain in context["domains"].values():

        lines.append(
            "- "
            + domain["label"]
            + ": "
            + str(domain["theoretical_score"])
            + " (theoretical estimate)"
        )

        correct = domain.get("correct_count")
        total = domain.get("item_count")

        if correct is not None and total is not None:

            lines.append(
                "  Observed performance: "
                + str(correct)
                + " of "
                + str(total)
                + " correct."
            )

    speed = context["processing_speed"]

    if speed["correct_per_minute"] is not None:

        lines.extend([
            "",
            "Processing speed: "
            + str(speed["correct_per_minute"])
            + " correct responses per minute.",
            "Processing speed is not included "
            "in the composite estimate.",
        ])

    lines.extend([
        "",
        "INTERPRETATION REQUIREMENTS",
        "",
        "These are experimental assessment results.",
        "They are not clinically validated IQ scores.",
        "They are not population-normed.",
        "Do not invent population percentiles.",
        "Do not infer psychological diagnoses.",
        "Do not equate cognitive ability with personality.",
        "Do not infer moral character or personal worth.",
        "Treat differences between domain scores cautiously.",
        "Do not assume small score differences are meaningful.",
        "Do not infer a person's learning style from scores.",
        "Do not assume occupational competence from scores.",
        "Use these results only when relevant to the question.",
        "Distinguish assessment performance from "
        "autobiographical evidence and inferred traits.",
        "When discussing intelligence explicitly, "
        "state the theoretical nature of the estimate.",
    ])

    return "\n".join(lines)

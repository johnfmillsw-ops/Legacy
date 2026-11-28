from cognitive_preferences import selected_result
from cognitive_storage import CognitiveAccessDenied


DOMAIN_LABELS = {
    "fluid_reasoning": "Fluid Reasoning",
    "visual_spatial": "Visual-Spatial Ability",
    "verbal_comprehension": "Verbal Comprehension",
    "quantitative_reasoning": "Quantitative Reasoning",
    "working_memory": "Working Memory",
    "processing_speed": "Processing Speed",
}


def build_cognitive_view(profile_id, owner_id, purpose):

    if purpose not in ("home", "cognitive_page"):
        raise ValueError("Invalid cognitive display purpose.")

    try:
        result = selected_result(
            profile_id,
            owner_id,
            purpose,
        )

    except CognitiveAccessDenied:
        return None

    if not result:
        return None

    estimate = result.get("estimated_iq")

    if estimate is None:
        return None

    domains = []

    for key, label in DOMAIN_LABELS.items():

        domain = result.get(
            "domain_results", {}
        ).get(key)

        if not domain:
            continue

        score = domain.get(
            "theoretical_scale_score"
        )

        domains.append({
            "key": key,
            "label": label,
            "score": (
                round(float(score))
                if score is not None
                else None
            ),
            "correct_per_minute": domain.get(
                "correct_per_minute"
            ),
        })

    return {
        "assessment_id": result["assessment_id"],
        "score": round(float(estimate)),
        "label": "Theoretical IQ-scale estimate",
        "qualification": (
            "Experimental · Not population-normed"
        ),
        "domains": domains,
        "completed_utc": result.get("completed_utc"),
        "scientifically_validated": False,
    }

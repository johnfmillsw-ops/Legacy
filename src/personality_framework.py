"""
Legacy permanent psychological assessment framework.

Trait expression:
    0 = strong evidence of low expression
    50 = balanced or moderate expression
    100 = strong evidence of high expression
    None = insufficient evidence

Evidence confidence is independent of trait expression.

Identity importance is not a personality measurement.
"""

FRAMEWORK_VERSION = 1

TRAIT_GROUPS = {
    "core_personality": {
        "openness": (
            "Preference for familiarity and convention",
            "Receptivity to novelty, imagination and ideas",
        ),
        "conscientiousness": (
            "Flexible or unstructured approach",
            "Organized, deliberate and dependable approach",
        ),
        "extraversion": (
            "Reserved and internally oriented",
            "Socially expressive and externally oriented",
        ),
        "agreeableness": (
            "Competitive and confrontational orientation",
            "Cooperative and accommodating orientation",
        ),
        "emotional_stability": (
            "Greater emotional reactivity",
            "Greater emotional steadiness",
        ),
    },

    "cognitive_style": {
        "analytical_thinking": (
            "Primarily intuitive reasoning",
            "Systematic and analytical reasoning",
        ),
        "intellectual_curiosity": (
            "Limited exploration of unfamiliar ideas",
            "Active pursuit of knowledge and understanding",
        ),
        "cognitive_flexibility": (
            "Preference for established interpretations",
            "Willingness to revise interpretations",
        ),
        "creativity": (
            "Preference for established solutions",
            "Generation of original approaches",
        ),
        "reflective_thinking": (
            "Limited deliberate self-reflection",
            "Frequent examination of thoughts and experiences",
        ),
    },

    "emotional_makeup": {
        "emotional_regulation": (
            "Difficulty modulating emotional responses",
            "Effective modulation of emotional responses",
        ),
        "emotional_sensitivity": (
            "Lower emotional responsiveness",
            "Heightened emotional responsiveness",
        ),
        "emotional_awareness": (
            "Limited recognition of emotional states",
            "Clear recognition of emotional states",
        ),
        "empathy": (
            "Limited perspective-taking",
            "Strong consideration of others' experiences",
        ),
        "resilience": (
            "Difficulty recovering from setbacks",
            "Demonstrated recovery and adaptation",
        ),
    },

    "character": {
        "integrity": (
            "Inconsistent adherence to stated principles",
            "Consistent adherence to stated principles",
        ),
        "accountability": (
            "Avoidance of personal responsibility",
            "Acceptance of personal responsibility",
        ),
        "loyalty": (
            "Limited sustained commitment",
            "Strong sustained commitment",
        ),
        "compassion": (
            "Limited concern for others' suffering",
            "Active concern for others' suffering",
        ),
        "courage": (
            "Avoidance of personally meaningful challenges",
            "Willingness to confront meaningful challenges",
        ),
        "humility": (
            "Resistance to acknowledging limitations",
            "Willingness to acknowledge limitations",
        ),
    },

    "interpersonal_psychology": {
        "interpersonal_trust": (
            "Interpersonal caution and distrust",
            "Willingness to place trust in others",
        ),
        "attachment_anxiety": (
            "Low concern about relational abandonment",
            "Heightened concern about relational abandonment",
        ),
        "attachment_avoidance": (
            "Comfort with emotional closeness",
            "Preference for emotional distance",
        ),
        "vulnerability": (
            "Reluctance to disclose emotional experiences",
            "Willingness to disclose emotional experiences",
        ),
        "assertiveness": (
            "Reluctance to express personal needs",
            "Direct expression of personal needs",
        ),
        "interpersonal_boundaries": (
            "Difficulty establishing personal boundaries",
            "Consistent establishment of personal boundaries",
        ),
    },

    "psychological_drives": {
        "autonomy": (
            "Preference for external direction",
            "Preference for self-direction",
        ),
        "achievement_drive": (
            "Limited emphasis on achievement",
            "Strong pursuit of achievement",
        ),
        "recognition_seeking": (
            "Limited need for external recognition",
            "Strong desire for external recognition",
        ),
        "belonging_need": (
            "Limited need for social affiliation",
            "Strong desire for social affiliation",
        ),
        "mastery_orientation": (
            "Limited pursuit of skill development",
            "Strong pursuit of competence and mastery",
        ),
        "internal_locus_of_control": (
            "Outcomes attributed primarily to external forces",
            "Outcomes attributed primarily to personal agency",
        ),
    },

    "behavioral_tendencies": {
        "self_discipline": (
            "Difficulty sustaining intentional behavior",
            "Consistent pursuit of intentional behavior",
        ),
        "persistence": (
            "Disengagement when encountering obstacles",
            "Sustained effort despite obstacles",
        ),
        "impulse_control": (
            "Immediate action with limited deliberation",
            "Deliberate control of immediate impulses",
        ),
        "risk_tolerance": (
            "Preference for predictable outcomes",
            "Willingness to accept uncertain outcomes",
        ),
        "adaptability": (
            "Difficulty adjusting to changing circumstances",
            "Effective adjustment to changing circumstances",
        ),
        "decisiveness": (
            "Difficulty committing to decisions",
            "Willingness to commit to decisions",
        ),
    },

    "psychological_vulnerabilities": {
        "rejection_sensitivity": (
            "Limited sensitivity to perceived rejection",
            "Heightened sensitivity to perceived rejection",
        ),
        "perfectionism": (
            "Acceptance of imperfect outcomes",
            "Demanding standards and concern over imperfections",
        ),
        "rumination": (
            "Limited repetitive negative reflection",
            "Persistent repetitive negative reflection",
        ),
        "need_for_control": (
            "Comfort with uncertainty and limited control",
            "Strong preference for predictability and control",
        ),
        "self_esteem": (
            "Lower expressed sense of self-worth",
            "Higher expressed sense of self-worth",
        ),
        "avoidance_tendency": (
            "Willingness to confront difficult experiences",
            "Tendency to avoid difficult experiences",
        ),
    },
}


TRAITS = {
    key: {
        "group": group,
        "label": key.replace("_", " ").title(),
        "low_expression": anchors[0],
        "high_expression": anchors[1],
    }
    for group, traits in TRAIT_GROUPS.items()
    for key, anchors in traits.items()
}


FORMULATION_AREAS = {
    "formative_experiences":
        "Experiences associated with psychological development.",

    "coping_strategies":
        "Recurring methods of managing distress and adversity.",

    "defense_mechanisms":
        "Possible protective psychological responses, "
        "distinguishing hypotheses from observed behavior.",

    "internal_conflicts":
        "Competing desires, beliefs, values and emotional needs.",

    "relationship_patterns":
        "Recurring interpersonal responses and relationship dynamics.",

    "core_beliefs":
        "Underlying beliefs about oneself, others and the world.",

    "fears_and_desires":
        "Expressed or evidence-supported fears and desires.",

    "decision_patterns":
        "Recurring approaches to judgment and decision-making.",

    "psychological_strengths":
        "Demonstrated psychological resources and strengths.",

    "psychological_blind_spots":
        "Possible inconsistencies between self-perception "
        "and demonstrated behavior.",

    "developmental_changes":
        "Changes in psychological patterns over time.",
}


def get_framework():
    return {
        "version": FRAMEWORK_VERSION,
        "traits": TRAITS,
        "formulation_areas": FORMULATION_AREAS,
    }


if __name__ == "__main__":
    print("LEGACY PERSONALITY FRAMEWORK")
    print("=" * 45)
    print("Framework version:", FRAMEWORK_VERSION)
    print("Psychological groups:", len(TRAIT_GROUPS))
    print("Individual psychological scales:", len(TRAITS))
    print("Deep formulation areas:", len(FORMULATION_AREAS))

    assert len(TRAITS) == sum(
        len(group) for group in TRAIT_GROUPS.values()
    )

    print("Framework validation passed.")
    print("No API requests made.")

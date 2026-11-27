"""
Legacy Psychological Identity Framework

Research-informed identity representation.
Not a clinical or standardized psychological assessment.
"""

FRAMEWORK_VERSION = 1

DIMENSIONS = {
    "cognition": {
        "label": "Cognition",
        "description": "How a person thinks, learns and reasons.",
        "characteristics": [
            "intellectual_curiosity",
            "analytical_thinking",
            "creativity",
            "problem_solving",
            "learning_orientation",
            "cognitive_flexibility",
            "abstract_reasoning",
            "spatial_reasoning",
        ],
    },

    "emotion": {
        "label": "Emotion",
        "description": "How a person experiences and expresses emotion.",
        "characteristics": [
            "emotional_intensity",
            "emotional_awareness",
            "emotional_expression",
            "emotional_regulation",
            "empathy",
            "optimism",
            "emotional_sensitivity",
            "emotional_resilience",
        ],
    },

    "motivation": {
        "label": "Motivation",
        "description": "The internal and external forces driving behavior.",
        "characteristics": [
            "achievement",
            "autonomy",
            "competence",
            "belonging",
            "recognition",
            "security",
            "mastery",
            "personal_growth",
            "contribution",
            "financial_motivation",
        ],
    },

    "personality": {
        "label": "Personality",
        "description": "Relatively enduring patterns of thought and behavior.",
        "characteristics": [
            "openness",
            "conscientiousness",
            "extraversion",
            "agreeableness",
            "emotional_stability",
            "assertiveness",
            "independence",
            "adaptability",
        ],
    },

    "attachment": {
        "label": "Attachment",
        "description": "How a person experiences interpersonal connection.",
        "characteristics": [
            "romantic_love",
            "familial_connection",
            "friendship",
            "trust",
            "intimacy",
            "loyalty",
            "commitment",
            "vulnerability",
            "interpersonal_boundaries",
        ],
    },

    "values": {
        "label": "Values",
        "description": "The principles that guide judgment and decisions.",
        "characteristics": [
            "integrity",
            "fairness",
            "freedom",
            "responsibility",
            "compassion",
            "tradition",
            "justice",
            "honor",
            "service",
            "self_direction",
        ],
    },

    "interests": {
        "label": "Interests",
        "description": "Activities and subjects that attract sustained interest.",
        "characteristics": [
            "sports",
            "physical_fitness",
            "technology",
            "science",
            "philosophy",
            "history",
            "music",
            "art",
            "literature",
            "nature",
            "travel",
            "entrepreneurship",
        ],
    },

    "social_identity": {
        "label": "Social identity",
        "description": "How a person understands their place in society.",
        "characteristics": [
            "family_roles",
            "professional_identity",
            "community",
            "cultural_identity",
            "leadership",
            "social_belonging",
            "mentorship",
            "group_affiliation",
        ],
    },

    "behavior": {
        "label": "Behavior",
        "description": "Observable patterns of action and decision-making.",
        "characteristics": [
            "discipline",
            "persistence",
            "risk_taking",
            "decision_making",
            "habit_formation",
            "initiative",
            "conflict_resolution",
            "cooperation",
            "response_to_adversity",
            "goal_directed_behavior",
        ],
    },

    "meaning": {
        "label": "Meaning",
        "description": "How a person understands the significance of life.",
        "characteristics": [
            "life_purpose",
            "personal_fulfillment",
            "worldview",
            "legacy",
            "spirituality",
            "future_aspirations",
            "personal_identity",
            "existential_reflection",
            "contribution_to_others",
        ],
    },
}


EVIDENCE_TYPES = (
    "direct_statement",
    "documented_assessment",
    "reported_behavior",
    "reported_experience",
    "user_confirmation",
    "ai_inference",
)


TEMPORAL_TYPES = (
    "temporary_state",
    "recurring_pattern",
    "enduring_characteristic",
    "unknown",
)


WEIGHT_FACTORS = {
    "personal_significance": 0.30,
    "behavioral_commitment": 0.25,
    "self_identification": 0.20,
    "continuity": 0.15,
    "emotional_significance": 0.10,
}


def calculate_identity_weight(factors):
    """
    Calculate an exploratory identity significance score.

    Missing factors remain unknown rather than being
    interpreted as zero.

    This is a provisional product heuristic, not a
    validated psychological measurement.
    """

    total = 0.0
    available_weight = 0.0

    for name, coefficient in WEIGHT_FACTORS.items():

        value = factors.get(name)

        if value is None:
            continue

        if isinstance(value, bool):
            raise ValueError("Boolean scores are invalid.")

        if not isinstance(value, (int, float)):
            raise ValueError("Scores must be numeric.")

        if not 0 <= value <= 100:
            raise ValueError("Scores must be between 0 and 100.")

        total += value * coefficient
        available_weight += coefficient

    # Require multiple factors and meaningful coverage.
    if available_weight < 0.50:
        return None

    return round(total / available_weight, 1)


def get_framework():

    return {
        "version": FRAMEWORK_VERSION,
        "dimensions": DIMENSIONS,
        "evidence_types": EVIDENCE_TYPES,
        "temporal_types": TEMPORAL_TYPES,
        "weight_factors": WEIGHT_FACTORS,
    }


if __name__ == "__main__":

    assert len(DIMENSIONS) == 10

    assert calculate_identity_weight({}) is None

    assert calculate_identity_weight({
        "personal_significance": 90
    }) is None

    assert calculate_identity_weight({
        "personal_significance": 80,
        "behavioral_commitment": 80,
    }) == 80.0

    print("Psychological framework validated.")
    print("Framework version:", FRAMEWORK_VERSION)
    print("Dimensions:", len(DIMENSIONS))

    print(
        "Initial characteristics:",
        sum(
            len(item["characteristics"])
            for item in DIMENSIONS.values()
        )
    )

    print("Weight calculation tests passed.")

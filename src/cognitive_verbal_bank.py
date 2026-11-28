
"""
Legacy Phase VII: Verbal knowledge bank.

Original, provisional linguistic content.
Difficulty assignments require empirical calibration.
"""

BANK_VERSION = 1

RELATIONSHIPS = {
    "young_of": (
        ("puppy", "dog"),
        ("kitten", "cat"),
        ("calf", "cow"),
        ("foal", "horse"),
        ("lamb", "sheep"),
        ("cygnet", "swan"),
    ),

    "instrument_measurement": (
        ("thermometer", "temperature"),
        ("barometer", "pressure"),
        ("speedometer", "speed"),
        ("compass", "direction"),
        ("chronometer", "time"),
        ("hygrometer", "humidity"),
    ),

    "professional_field": (
        ("botanist", "plants"),
        ("zoologist", "animals"),
        ("geologist", "rocks"),
        ("astronomer", "celestial objects"),
        ("entomologist", "insects"),
        ("ornithologist", "birds"),
    ),

    "material_product": (
        ("clay", "pottery"),
        ("wool", "yarn"),
        ("wood", "paper"),
        ("sand", "glass"),
        ("milk", "cheese"),
        ("grapes", "raisins"),
    ),

    "object_function": (
        ("scissors", "cutting"),
        ("broom", "sweeping"),
        ("needle", "sewing"),
        ("eraser", "erasing"),
        ("sieve", "straining"),
        ("telescope", "magnifying distant objects"),
    ),
}

SYNONYMS = {
    1: (
        ("happy", "joyful"),
        ("large", "big"),
        ("small", "little"),
        ("quick", "fast"),
        ("silent", "quiet"),
        ("begin", "start"),
    ),

    2: (
        ("cautious", "careful"),
        ("scarce", "rare"),
        ("assist", "help"),
        ("fragile", "delicate"),
        ("accurate", "correct"),
        ("essential", "necessary"),
    ),

    3: (
        ("reluctant", "hesitant"),
        ("abundant", "plentiful"),
        ("concise", "brief"),
        ("impartial", "unbiased"),
        ("resilient", "adaptable"),
        ("diligent", "industrious"),
    ),

    4: (
        ("ambiguous", "unclear"),
        ("pragmatic", "practical"),
        ("meticulous", "painstaking"),
        ("benevolent", "kindhearted"),
        ("coherent", "consistent"),
        ("transient", "temporary"),
    ),

    5: (
        ("ephemeral", "short-lived"),
        ("obdurate", "unyielding"),
        ("perspicacious", "discerning"),
        ("laconic", "terse"),
        ("equivocal", "ambiguous"),
        ("assiduous", "diligent"),
    ),
}

ANTONYMS = {
    1: (
        ("hot", "cold"),
        ("early", "late"),
        ("empty", "full"),
        ("wide", "narrow"),
        ("light", "heavy"),
        ("wet", "dry"),
    ),

    2: (
        ("expand", "contract"),
        ("accept", "reject"),
        ("increase", "decrease"),
        ("include", "exclude"),
        ("permit", "forbid"),
        ("advance", "retreat"),
    ),

    3: (
        ("optimistic", "pessimistic"),
        ("voluntary", "compulsory"),
        ("permanent", "temporary"),
        ("explicit", "implicit"),
        ("abundant", "scarce"),
        ("flexible", "rigid"),
    ),

    4: (
        ("benevolent", "malevolent"),
        ("coherent", "incoherent"),
        ("conspicuous", "inconspicuous"),
        ("meticulous", "careless"),
        ("credible", "implausible"),
        ("impartial", "biased"),
    ),

    5: (
        ("gregarious", "unsociable"),
        ("magnanimous", "petty"),
        ("prolific", "unproductive"),
        ("parsimonious", "extravagant"),
        ("recalcitrant", "compliant"),
        ("equanimity", "agitation"),
    ),
}

CATEGORIES = {
    "mammals": (
        "elephant", "whale", "tiger",
        "dolphin", "bat", "horse",
        "rabbit", "giraffe",
    ),

    "birds": (
        "eagle", "sparrow", "penguin",
        "ostrich", "falcon", "owl",
        "swan", "pelican",
    ),

    "metals": (
        "iron", "copper", "silver",
        "gold", "aluminum", "zinc",
        "nickel", "titanium",
    ),

    "geometric_shapes": (
        "triangle", "square", "pentagon",
        "hexagon", "circle", "ellipse",
        "rectangle", "octagon",
    ),

    "musical_instruments": (
        "violin", "trumpet", "flute",
        "clarinet", "cello", "trombone",
        "oboe", "bassoon",
    ),

    "chemical_elements": (
        "oxygen", "hydrogen", "helium",
        "carbon", "nitrogen", "neon",
        "argon", "chlorine",
    ),

    "units_of_length": (
        "meter", "centimeter", "kilometer",
        "inch", "foot", "yard",
        "mile", "millimeter",
    ),

    "units_of_time": (
        "second", "minute", "hour",
        "day", "week", "month",
        "year", "decade",
    ),

    "literary_forms": (
        "novel", "sonnet", "haiku",
        "novella", "fable", "epic",
        "ballad", "limerick",
    ),

    "logical_connectives": (
        "conjunction", "disjunction",
        "negation", "implication",
        "biconditional",
    ),
}


def validate_bank():
    assert set(SYNONYMS) == set(range(1, 6))
    assert set(ANTONYMS) == set(range(1, 6))

    for relation, pairs in RELATIONSHIPS.items():
        assert len(pairs) >= 5
        assert len(set(pairs)) == len(pairs)

        assert len({
            left for left, right in pairs
        }) == len(pairs)

        assert len({
            right for left, right in pairs
        }) == len(pairs)

    print("Relationship bank structure: PASSED")

    for bank in (SYNONYMS, ANTONYMS):
        for level, pairs in bank.items():
            assert len(pairs) >= 5
            assert len(set(pairs)) == len(pairs)

            for left, right in pairs:
                assert left.strip()
                assert right.strip()
                assert left.casefold() != right.casefold()

    print("Vocabulary bank structure: PASSED")

    for category, words in CATEGORIES.items():
        assert len(words) >= 5
        assert len(set(words)) == len(words)
        assert all(word.strip() for word in words)

    print("Concept classification structure: PASSED")

    print()
    print("Relationship pairs:", sum(
        len(pairs)
        for pairs in RELATIONSHIPS.values()
    ))

    print("Synonym pairs:", sum(
        len(pairs)
        for pairs in SYNONYMS.values()
    ))

    print("Antonym pairs:", sum(
        len(pairs)
        for pairs in ANTONYMS.values()
    ))

    print("Concept categories:", len(CATEGORIES))

    print("Classification entries:", sum(
        len(words)
        for words in CATEGORIES.values()
    ))

    print()
    print("ALL VERBAL BANK STRUCTURAL TESTS PASSED")


if __name__ == "__main__":
    validate_bank()

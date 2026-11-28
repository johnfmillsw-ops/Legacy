
"""
Legacy Phase VII: Standardized timing protocol.

Versioned experimental administration rules.
Timing budgets are provisional, not calibrated norms.
"""

from copy import deepcopy
import math

TIMING_VERSION = 1

PROTOCOL_STATUS = "experimental"

TARGET_DURATION_MS = 60 * 60 * 1000

INSTRUCTION_BUDGET_MS = 5 * 60 * 1000

DOMAIN_PROTOCOLS = {
    "fluid_reasoning": {
        "budget_ms": 12 * 60 * 1000,
        "timing_mode": "guideline",
    },
    "visual_spatial": {
        "budget_ms": 10 * 60 * 1000,
        "timing_mode": "guideline",
    },
    "verbal_comprehension": {
        "budget_ms": 7 * 60 * 1000,
        "timing_mode": "guideline",
    },
    "quantitative_reasoning": {
        "budget_ms": 12 * 60 * 1000,
        "timing_mode": "guideline",
    },
    "working_memory": {
        "budget_ms": 8 * 60 * 1000,
        "timing_mode": "controlled_exposure",
    },
    "processing_speed": {
        "budget_ms": 6 * 60 * 1000,
        "timing_mode": "strict_blocks",
    },
}

SPEED_BLOCKS = {
    "symbol_comparison": 120000,
    "visual_discrimination": 120000,
    "pattern_matching": 120000,
}

MEMORY_EXPOSURE_MS = {
    1: 4000,
    2: 5000,
    3: 6000,
    4: 7000,
    5: 8000,
}

RESPONSE_OUTCOMES = (
    "correct",
    "incorrect",
    "timed_out",
    "not_reached",
)

INTERRUPTION_TYPES = (
    "visibility_lost",
    "window_focus_lost",
    "network_interruption",
    "rendering_delay",
    "page_reload",
    "device_sleep",
    "user_requested_break",
)


def validate_ms(value, name):
    if type(value) is not int:
        raise ValueError(
            f"{name} must be integer milliseconds."
        )

    if value < 0:
        raise ValueError(
            f"{name} cannot be negative."
        )

    return value


def get_timing_protocol():
    return {
        "timing_version": TIMING_VERSION,
        "status": PROTOCOL_STATUS,
        "target_duration_ms": TARGET_DURATION_MS,
        "instruction_budget_ms":
            INSTRUCTION_BUDGET_MS,
        "domains": deepcopy(DOMAIN_PROTOCOLS),
        "speed_blocks": deepcopy(SPEED_BLOCKS),
        "memory_exposure_ms":
            deepcopy(MEMORY_EXPOSURE_MS),
        "global_hard_deadline": False,
        "calibrated": False,
    }


def domain_protocol(domain):
    if domain not in DOMAIN_PROTOCOLS:
        raise ValueError(
            "Unknown cognitive domain."
        )

    return deepcopy(
        DOMAIN_PROTOCOLS[domain]
    )


def speed_block_duration(family):
    if family not in SPEED_BLOCKS:
        raise ValueError(
            "Unknown processing speed family."
        )

    return SPEED_BLOCKS[family]


def memory_exposure_duration(difficulty):
    if (
        type(difficulty) is not int
        or difficulty not in MEMORY_EXPOSURE_MS
    ):
        raise ValueError(
            "Invalid memory difficulty."
        )

    return MEMORY_EXPOSURE_MS[difficulty]


def elapsed_ms(started_ms, current_ms):
    validate_ms(started_ms, "Start time")
    validate_ms(current_ms, "Current time")

    if current_ms < started_ms:
        raise ValueError(
            "Clock moved backwards."
        )

    return current_ms - started_ms


def block_deadline(started_ms, family):
    validate_ms(started_ms, "Block start")

    return (
        started_ms
        + speed_block_duration(family)
    )


def remaining_ms(deadline_ms, current_ms):
    validate_ms(deadline_ms, "Deadline")
    validate_ms(current_ms, "Current time")

    return max(
        0, deadline_ms - current_ms
    )


def deadline_reached(deadline_ms, current_ms):
    return remaining_ms(
        deadline_ms, current_ms
    ) == 0


def memory_exposure_complete(
    started_ms,
    current_ms,
    difficulty,
):
    return elapsed_ms(
        started_ms, current_ms
    ) >= memory_exposure_duration(
        difficulty
    )


def classify_response(
    *,
    presented,
    correct=None,
    submitted_ms=None,
    deadline_ms=None,
    closed_ms=None,
):
    if type(presented) is not bool:
        raise ValueError(
            "Invalid presentation status."
        )

    if deadline_ms is not None:
        validate_ms(
            deadline_ms, "Deadline"
        )

    if closed_ms is not None:
        validate_ms(
            closed_ms, "Closure time"
        )

    if not presented:
        if (
            submitted_ms is not None
            or correct is not None
        ):
            raise ValueError(
                "Unpresented item has a response."
            )

        if (
            deadline_ms is not None
            and closed_ms is not None
            and closed_ms >= deadline_ms
        ):
            return "not_reached"

        raise ValueError(
            "Unpresented item is not finalized."
        )

    if submitted_ms is None:
        if correct is not None:
            raise ValueError(
                "Missing response timestamp."
            )

        if (
            deadline_ms is not None
            and closed_ms is not None
            and closed_ms >= deadline_ms
        ):
            return "timed_out"

        raise ValueError(
            "Response remains pending."
        )

    validate_ms(
        submitted_ms, "Submission time"
    )

    if type(correct) is not bool:
        raise ValueError(
            "Response requires correctness."
        )

    if (
        deadline_ms is not None
        and submitted_ms >= deadline_ms
    ):
        return "timed_out"

    return (
        "correct" if correct
        else "incorrect"
    )


def validate_latency(value, name):
    if type(value) not in (int, float):
        raise ValueError(
            f"Invalid {name}."
        )

    if not math.isfinite(value):
        raise ValueError(
            f"Nonfinite {name}."
        )

    if value < 0:
        raise ValueError(
            f"Negative {name}."
        )

    return float(value)


def timing_observation(
    *,
    server_elapsed_ms,
    client_elapsed_ms=None,
    interruptions=(),
    device_type="unknown",
    input_method="unknown",
):
    validate_ms(
        server_elapsed_ms,
        "Server elapsed time",
    )

    if client_elapsed_ms is not None:
        client_elapsed_ms = validate_latency(
            client_elapsed_ms,
            "Client elapsed time",
        )

    interruptions = tuple(interruptions)

    if any(
        event not in INTERRUPTION_TYPES
        for event in interruptions
    ):
        raise ValueError(
            "Unknown interruption type."
        )

    if device_type not in (
        "desktop",
        "laptop",
        "tablet",
        "mobile",
        "unknown",
    ):
        raise ValueError(
            "Unknown device type."
        )

    if input_method not in (
        "mouse",
        "trackpad",
        "touch",
        "keyboard",
        "assistive",
        "unknown",
    ):
        raise ValueError(
            "Unknown input method."
        )

    flags = []

    if client_elapsed_ms is None:
        flags.append(
            "missing_client_timing"
        )

    if interruptions:
        flags.append(
            "interrupted_administration"
        )

    if device_type == "unknown":
        flags.append(
            "unknown_device"
        )

    if input_method == "unknown":
        flags.append(
            "unknown_input_method"
        )

    difference = None

    if client_elapsed_ms is not None:
        difference = (
            server_elapsed_ms
            - client_elapsed_ms
        )

    return {
        "timing_version": TIMING_VERSION,
        "server_elapsed_ms": server_elapsed_ms,
        "client_elapsed_ms": client_elapsed_ms,
        "clock_difference_ms": difference,
        "interruptions": list(interruptions),
        "device_type": device_type,
        "input_method": input_method,
        "quality_flags": flags,
        "requires_review": bool(flags),
        "scientifically_validated": False,
    }


def run_tests():
    from cognitive_memory import PRESENTATION_MS
    from cognitive_framework import COGNITIVE_DOMAINS

    assert set(DOMAIN_PROTOCOLS) == set(
        COGNITIVE_DOMAINS
    )

    total = sum(
        protocol["budget_ms"]
        for protocol in DOMAIN_PROTOCOLS.values()
    )

    assert (
        total + INSTRUCTION_BUDGET_MS
        == TARGET_DURATION_MS
    )

    print("60-minute pilot budget: PASSED")

    assert sum(SPEED_BLOCKS.values()) == (
        DOMAIN_PROTOCOLS[
            "processing_speed"
        ]["budget_ms"]
    )

    print("Processing speed block allocation: PASSED")

    assert MEMORY_EXPOSURE_MS == PRESENTATION_MS

    print("Memory generator timing alignment: PASSED")

    for family in SPEED_BLOCKS:
        started = 10000

        deadline = block_deadline(
            started, family
        )

        assert deadline == 130000

        assert remaining_ms(
            deadline, started
        ) == 120000

        assert not deadline_reached(
            deadline, deadline - 1
        )

        assert deadline_reached(
            deadline, deadline
        )

        assert deadline_reached(
            deadline, deadline + 1
        )

    print("Strict deadline boundaries: PASSED")

    for difficulty in range(1, 6):
        duration = memory_exposure_duration(
            difficulty
        )

        assert not memory_exposure_complete(
            1000,
            1000 + duration - 1,
            difficulty,
        )

        assert memory_exposure_complete(
            1000,
            1000 + duration,
            difficulty,
        )

    print("Controlled memory exposure: PASSED")

    assert classify_response(
        presented=True,
        correct=True,
        submitted_ms=999,
        deadline_ms=1000,
    ) == "correct"

    assert classify_response(
        presented=True,
        correct=False,
        submitted_ms=999,
        deadline_ms=1000,
    ) == "incorrect"

    assert classify_response(
        presented=True,
        correct=True,
        submitted_ms=1000,
        deadline_ms=1000,
    ) == "timed_out"

    assert classify_response(
        presented=True,
        deadline_ms=1000,
        closed_ms=1000,
    ) == "timed_out"

    assert classify_response(
        presented=False,
        deadline_ms=1000,
        closed_ms=1000,
    ) == "not_reached"

    assert classify_response(
        presented=True,
        correct=True,
        submitted_ms=5000,
    ) == "correct"

    print("Distinct response outcomes: PASSED")

    clean = timing_observation(
        server_elapsed_ms=1500,
        client_elapsed_ms=1450.5,
        device_type="laptop",
        input_method="trackpad",
    )

    assert clean["clock_difference_ms"] == 49.5

    assert not clean["requires_review"]

    assert not clean["scientifically_validated"]

    interrupted = timing_observation(
        server_elapsed_ms=1500,
        client_elapsed_ms=1400,
        interruptions=("visibility_lost",),
        device_type="laptop",
        input_method="trackpad",
    )

    assert interrupted["requires_review"]

    assert (
        "interrupted_administration"
        in interrupted["quality_flags"]
    )

    missing = timing_observation(
        server_elapsed_ms=1500,
    )

    assert missing["requires_review"]

    print("Timing quality observations: PASSED")

    invalid_cases = (
        lambda: elapsed_ms(100, 99),
        lambda: elapsed_ms(-1, 100),
        lambda: elapsed_ms(True, 100),
        lambda: memory_exposure_duration(0),
        lambda: memory_exposure_duration(True),
        lambda: speed_block_duration("unknown"),
        lambda: classify_response(
            presented=True,
            deadline_ms=1000,
            closed_ms=999,
        ),
        lambda: classify_response(
            presented=False,
            correct=True,
            submitted_ms=500,
        ),
        lambda: classify_response(
            presented=False,
        ),
        lambda: timing_observation(
            server_elapsed_ms=100,
            client_elapsed_ms=float("nan"),
        ),
        lambda: timing_observation(
            server_elapsed_ms=100,
            client_elapsed_ms=-1,
        ),
        lambda: timing_observation(
            server_elapsed_ms=100,
            interruptions=("unknown",),
        ),
    )

    for operation in invalid_cases:
        try:
            operation()
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Invalid timing input accepted."
            )

    print("12 invalid-input controls: PASSED")

    protocol = get_timing_protocol()

    protocol["domains"].clear()
    protocol["speed_blocks"].clear()

    assert len(
        get_timing_protocol()["domains"]
    ) == 6

    assert len(
        get_timing_protocol()["speed_blocks"]
    ) == 3

    print("Protocol mutation isolation: PASSED")

    print()
    print("ALL STANDARDIZED TIMING TESTS PASSED")


if __name__ == "__main__":
    run_tests()

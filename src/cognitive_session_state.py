
"""
Legacy Phase VII: Persistent assessment state.

Explicit, versioned serialization.
No pickle or arbitrary object deserialization.
Server-side use only.
"""

from copy import deepcopy

from cognitive_engine import fingerprint

from cognitive_session import (
    AssessmentSession,
    SESSION_VERSION,
)

from cognitive_item_identity import (
    verify_item_record,
)

STATE_VERSION = 1

VALID_STATES = {
    "ready",
    "memorize",
    "respond",
    "answered",
    "completed",
    "interrupted",
}

STATE_FIELDS = (
    "session_id",
    "form_id",
    "created_ms",
    "last_event_ms",
    "block_index",
    "item_index",
    "state",
    "block_started_ms",
    "block_deadline_ms",
    "presented_ms",
    "response_started_ms",
    "responses",
    "exposures",
    "block_results",
    "interruptions",
    "completed_ms",
)


class StateIntegrityError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise StateIntegrityError(message)


def valid_ms(value):
    return type(value) is int and value >= 0


def serialize_session(session):
    require(
        isinstance(session, AssessmentSession),
        "Invalid assessment session.",
    )

    payload = {
        "state_version": STATE_VERSION,
        "session_version": SESSION_VERSION,
        "blocks_hash": fingerprint(
            session.blocks
        ),
        "state": {
            field: deepcopy(
                getattr(session, field)
            )
            for field in STATE_FIELDS
        },
    }

    return {
        "payload": payload,
        "integrity_hash": fingerprint(payload),
    }


def restore_session(snapshot, blocks):
    if not __debug__:
        raise RuntimeError(
            "Question verification requires assertions."
        )

    require(
        isinstance(snapshot, dict),
        "Invalid state snapshot.",
    )

    require(
        set(snapshot) == {
            "payload",
            "integrity_hash",
        },
        "Unexpected snapshot fields.",
    )

    payload = snapshot["payload"]

    require(
        fingerprint(payload)
        == snapshot["integrity_hash"],
        "State integrity mismatch.",
    )

    require(
        payload["state_version"]
        == STATE_VERSION,
        "Unsupported state version.",
    )

    require(
        payload["session_version"]
        == SESSION_VERSION,
        "Unsupported session version.",
    )

    require(
        fingerprint(blocks)
        == payload["blocks_hash"],
        "Assessment blocks changed.",
    )

    state = payload["state"]

    require(
        set(state) == set(STATE_FIELDS),
        "Unexpected session fields.",
    )

    require(
        state["state"] in VALID_STATES,
        "Unknown assessment state.",
    )

    for field in (
        "session_id",
        "form_id",
    ):
        require(
            isinstance(state[field], str)
            and bool(state[field]),
            f"Invalid identity: {field}",
        )

    require(
        valid_ms(state["created_ms"])
        and valid_ms(state["last_event_ms"]),
        "Invalid session timestamps.",
    )

    require(
        state["last_event_ms"]
        >= state["created_ms"],
        "Invalid session clock.",
    )

    for field in (
        "block_started_ms",
        "block_deadline_ms",
        "presented_ms",
        "response_started_ms",
        "completed_ms",
    ):
        value = state[field]

        require(
            value is None or valid_ms(value),
            f"Invalid timestamp: {field}",
        )

    require(
        isinstance(blocks, list)
        and bool(blocks),
        "Assessment blocks missing.",
    )

    items = {}

    for block_index, block in enumerate(blocks):
        require(
            block["item_count"]
            == len(block["items"]),
            "Block item count mismatch.",
        )

        for item_index, record in enumerate(
            block["items"]
        ):
            verify_item_record(record)

            items[
                (block_index, item_index)
            ] = record

    block_index = state["block_index"]
    item_index = state["item_index"]

    require(
        type(block_index) is int
        and 0 <= block_index <= len(blocks),
        "Invalid block position.",
    )

    require(
        type(item_index) is int
        and item_index >= 0,
        "Invalid item position.",
    )

    completed = state["state"] == "completed"

    if completed:
        require(
            block_index == len(blocks)
            and item_index == 0,
            "Invalid completed position.",
        )

        require(
            state["completed_ms"]
            is not None,
            "Missing completion time.",
        )

        require(
            state["created_ms"]
            <= state["completed_ms"]
            <= state["last_event_ms"],
            "Invalid completion time.",
        )

    else:
        require(
            block_index < len(blocks),
            "Active block missing.",
        )

        require(
            item_index
            < blocks[block_index]["item_count"],
            "Active item missing.",
        )

        require(
            state["completed_ms"] is None,
            "Premature completion time.",
        )

    for field in (
        "responses",
        "exposures",
        "block_results",
        "interruptions",
    ):
        require(
            isinstance(state[field], list),
            f"Invalid collection: {field}",
        )

    require(
        len(state["block_results"])
        == block_index,
        "Completed block count mismatch.",
    )

    seen_responses = set()

    for response in state["responses"]:
        position = (
            response["block_index"],
            response["item_index"],
        )

        require(
            position in items,
            "Response references unknown item.",
        )

        require(
            position not in seen_responses,
            "Duplicate stored response.",
        )

        seen_responses.add(position)

        record = items[position]
        question = record["question_snapshot"]

        require(
            response["item_id"]
            == record["item_id"]
            and response["presentation_id"]
            == record["presentation_id"]
            and response["question_id"]
            == question["id"],
            "Stored response identity mismatch.",
        )

        outcome = response["outcome"]

        require(
            outcome in (
                "correct",
                "incorrect",
                "timed_out",
                "not_reached",
            ),
            "Invalid response outcome.",
        )

        if outcome in ("correct", "incorrect"):
            selected = response[
                "selected_option_id"
            ]

            require(
                selected in {
                    option["id"]
                    for option in question["options"]
                },
                "Invalid stored answer.",
            )

            correct = (
                selected
                == question["correct_option_id"]
            )

            require(
                response["correct"] is correct
                and outcome == (
                    "correct"
                    if correct
                    else "incorrect"
                ),
                "Stored answer scoring mismatch.",
            )

        else:
            require(
                response["correct"] is None
                and response["selected_option_id"]
                is None,
                "Unexpected unanswered-item score.",
            )

    if completed:
        require(
            len(seen_responses) == len(items),
            "Completed assessment has missing outcomes.",
        )

    known_exposures = {
        record["item_id"]: record
        for record in items.values()
    }

    seen_exposures = set()

    for exposure in state["exposures"]:
        item_id = exposure["item_id"]

        require(
            item_id in known_exposures,
            "Unknown exposed item.",
        )

        require(
            item_id not in seen_exposures,
            "Duplicate item exposure.",
        )

        seen_exposures.add(item_id)

        record = known_exposures[item_id]

        require(
            exposure["presentation_id"]
            == record["presentation_id"]
            and exposure["exposure_hash"]
            == record["question_snapshot"][
                "exposure_hash"
            ],
            "Exposure identity mismatch.",
        )

    if state["state"] in (
        "memorize",
        "respond",
        "answered",
    ):
        record = items[
            (block_index, item_index)
        ]

        require(
            record["item_id"]
            in seen_exposures,
            "Active item was not exposed.",
        )

        require(
            state["presented_ms"] is not None,
            "Active presentation time missing.",
        )

        require(
            state["block_started_ms"] is not None,
            "Active block start missing.",
        )

        duration = blocks[
            block_index
        ]["duration_ms"]

        expected_deadline = (
            state["block_started_ms"] + duration
            if duration is not None
            else None
        )

        require(
            state["block_deadline_ms"]
            == expected_deadline,
            "Stored block deadline mismatch.",
        )

        if state["state"] == "answered":
            require(
                (block_index, item_index)
                in seen_responses,
                "Answered item has no response.",
            )

        else:
            require(
                (block_index, item_index)
                not in seen_responses,
                "Active item already answered.",
            )

    # Reconstruct only the known session class
    # and explicitly permitted state fields.
    session = AssessmentSession.__new__(
        AssessmentSession
    )

    session.blocks = deepcopy(blocks)

    for field in STATE_FIELDS:
        setattr(
            session,
            field,
            deepcopy(state[field]),
        )

    return session


def run_tests():
    import json

    from cognitive_research_bank import (
        build_research_bank,
    )

    from cognitive_blueprint import (
        assemble_assessment,
    )

    from cognitive_timing import (
        memory_exposure_duration,
    )

    from test_cognitive_database import (
        complete_session,
    )

    bank = build_research_bank()

    form = assemble_assessment(
        bank,
        "persistent-state-test-v1",
    )

    session = AssessmentSession(
        form, bank, 1000
    )

    def roundtrip(original):
        snapshot = serialize_session(
            original
        )

        snapshot = json.loads(
            json.dumps(snapshot)
        )

        restored = restore_session(
            snapshot,
            original.blocks,
        )

        require(
            serialize_session(restored)
            == serialize_session(original),
            "State roundtrip mismatch.",
        )

        require(
            restored.status()
            == original.status(),
            "Restored status mismatch.",
        )

        return restored

    session = roundtrip(session)

    print("Initial state reconstruction: PASSED")

    session.begin_block(1000)

    session = roundtrip(session)

    question = session._question()

    session.submit_response(
        question["id"],
        question["correct_option_id"],
        2000,
    )

    session = roundtrip(session)

    require(
        len(session.responses) == 1,
        "Stored response lost.",
    )

    session.advance(2100)

    session = roundtrip(session)

    print("Response and progression persistence: PASSED")

    now = 2100
    memory_checked = False
    speed_checked = False

    while session.state != "completed":

        if session.state == "ready":
            now += 1000

            session.begin_block(now)

            if session._block()["mode"] == (
                "timed_queue"
            ):
                deadline = (
                    session.block_deadline_ms
                )

                session = roundtrip(session)

                require(
                    session.block_deadline_ms
                    == deadline,
                    "Deadline reset during restore.",
                )

                speed_checked = True

                now = deadline

                session.tick(now)

                session = roundtrip(session)

                continue

        elif session.state == "memorize":
            session = roundtrip(session)

            question = session._question()

            now += memory_exposure_duration(
                question["difficulty"]
            )

            session.finish_memory_exposure(
                question["id"],
                now,
            )

            session = roundtrip(session)

            memory_checked = True

        elif session.state == "respond":
            question = session._question()

            now += 1000

            session.submit_response(
                question["id"],
                question["correct_option_id"],
                now,
            )

        elif session.state == "answered":
            now += 100

            session.advance(now)

        else:
            raise StateIntegrityError(
                "Unexpected assessment state."
            )

    require(
        memory_checked,
        "Memory persistence not exercised.",
    )

    require(
        speed_checked,
        "Speed persistence not exercised.",
    )

    print("Memory exposure state persistence: PASSED")
    print("Timed block deadline preservation: PASSED")

    results = session.results()

    session = roundtrip(session)

    require(
        session.results() == results,
        "Completed results changed.",
    )

    print("Completed result reconstruction: PASSED")

    snapshot = serialize_session(session)

    def reject(candidate, blocks):
        try:
            restore_session(
                candidate, blocks
            )

        except StateIntegrityError:
            return

        raise AssertionError(
            "Invalid state accepted."
        )

    changed = deepcopy(snapshot)

    changed["payload"]["state"][
        "last_event_ms"
    ] += 1000

    reject(changed, session.blocks)

    print("Snapshot corruption detection: PASSED")

    changed = deepcopy(snapshot)

    changed["payload"]["state"][
        "responses"
    ].append(
        deepcopy(
            session.responses[0]
        )
    )

    changed["integrity_hash"] = fingerprint(
        changed["payload"]
    )

    reject(changed, session.blocks)

    print("Duplicate stored response detection: PASSED")

    changed = deepcopy(snapshot)

    response = changed["payload"]["state"][
        "responses"
    ][0]

    response["correct"] = not response[
        "correct"
    ]

    changed["integrity_hash"] = fingerprint(
        changed["payload"]
    )

    reject(changed, session.blocks)

    print("Stored scoring consistency: PASSED")

    changed_blocks = deepcopy(
        session.blocks
    )

    changed_blocks[0]["items"][0][
        "question_snapshot"
    ]["prompt"] = "Changed question."

    reject(snapshot, changed_blocks)

    print("Question snapshot integrity: PASSED")

    restored = restore_session(
        snapshot,
        session.blocks,
    )

    restored.responses.clear()

    require(
        bool(session.responses)
        and bool(
            snapshot["payload"]["state"][
                "responses"
            ]
        ),
        "Restored state shares mutable references.",
    )

    print("State mutation isolation: PASSED")

    print()
    print("ALL SESSION PERSISTENCE TESTS PASSED")


if __name__ == "__main__":
    run_tests()

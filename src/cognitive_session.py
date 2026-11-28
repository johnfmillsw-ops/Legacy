
"""
Legacy Phase VII: Experimental assessment sessions.

Server-side assessment state machine.
No client-authorized scoring or progression.
No IQ or clinical reporting.
"""

from copy import deepcopy
from collections import Counter
from uuid import uuid4

from cognitive_blueprint import (
    verify_assessment,
)

from cognitive_registry import (
    presentation_question,
    response_question,
    evaluate_response,
    MEMORY_FAMILIES,
)

from cognitive_timing import (
    validate_ms,
    memory_exposure_duration,
)

SESSION_VERSION = 1


class SessionStateError(RuntimeError):
    pass


class AssessmentSession:
    def __init__(self, form, bank, now_ms):
        if not __debug__:
            raise RuntimeError(
                "Question verification requires "
                "Python assertions."
            )

        validate_ms(now_ms, "Creation time")

        verify_assessment(form, bank)

        self.session_id = uuid4().hex
        self.form_id = form["form_id"]
        self.created_ms = now_ms
        self.last_event_ms = now_ms

        self.blocks = []

        for section in form["sections"]:
            for block in section["blocks"]:
                self.blocks.append({
                    **deepcopy(block),
                    "domain": section["domain"],
                })

        self.block_index = 0
        self.item_index = 0

        self.state = "ready"

        self.block_started_ms = None
        self.block_deadline_ms = None
        self.presented_ms = None
        self.response_started_ms = None

        self.responses = []
        self.exposures = []
        self.block_results = []
        self.interruptions = []

        self.completed_ms = None

    def _clock(self, now_ms):
        validate_ms(now_ms, "Event time")

        if now_ms < self.last_event_ms:
            raise SessionStateError(
                "Event clock moved backwards."
            )

        self.last_event_ms = now_ms

    def _block(self):
        if self.block_index >= len(self.blocks):
            raise SessionStateError(
                "No active assessment block."
            )

        return self.blocks[self.block_index]

    def _record(self):
        return self._block()["items"][
            self.item_index
        ]

    def _question(self):
        return self._record()[
            "question_snapshot"
        ]

    def _require_state(self, *states):
        if self.state not in states:
            raise SessionStateError(
                f"Operation unavailable in "
                f"state: {self.state}"
            )

    def _expired(self, now_ms):
        return (
            self.block_deadline_ms is not None
            and now_ms >= self.block_deadline_ms
        )

    def status(self):
        result = {
            "session_id": self.session_id,
            "form_id": self.form_id,
            "session_version": SESSION_VERSION,
            "state": self.state,
            "block_number": min(
                self.block_index + 1,
                len(self.blocks),
            ),
            "total_blocks": len(self.blocks),
            "qualification_status": "experimental",
            "iq_reporting_enabled": False,
        }

        if self.state not in (
            "completed", "interrupted"
        ):
            block = self._block()

            result.update({
                "domain": block["domain"],
                "family": block["family"],
                "mode": block["mode"],
                "item_number": self.item_index + 1,
                "block_item_count":
                    block["item_count"],
                "block_duration_ms":
                    block["duration_ms"],
                "block_deadline_ms":
                    self.block_deadline_ms,
            })

        return result

    def begin_block(self, now_ms):
        self._require_state("ready")
        self._clock(now_ms)

        block = self._block()

        self.block_started_ms = now_ms

        duration = block["duration_ms"]

        self.block_deadline_ms = (
            now_ms + duration
            if duration is not None
            else None
        )

        return self._present(now_ms)

    def _present(self, now_ms):
        if self._expired(now_ms):
            self._finish_block(
                now_ms, "deadline"
            )
            return self.status()

        record = self._record()
        question = self._question()

        self.presented_ms = now_ms
        self.response_started_ms = None

        self.exposures.append({
            "item_id": record["item_id"],
            "presentation_id":
                record["presentation_id"],
            "exposure_hash":
                question["exposure_hash"],
            "presented_ms": now_ms,
        })

        payload = presentation_question(
            question
        )

        if question["family"] in MEMORY_FAMILIES:
            self.state = "memorize"

            # Manipulation instructions must be
            # available before stimulus exposure.
            if question["family"] == (
                "sequence_manipulation"
            ):
                payload[
                    "response_instruction"
                ] = question["prompt"]

            payload["exposure_duration_ms"] = (
                memory_exposure_duration(
                    question["difficulty"]
                )
            )

        else:
            self.state = "respond"
            self.response_started_ms = now_ms

        return {
            **self.status(),
            "question": payload,
        }

    def finish_memory_exposure(
        self,
        question_id,
        now_ms,
    ):
        self._require_state("memorize")

        question = self._question()

        if question_id != question["id"]:
            raise SessionStateError(
                "Stale question identity."
            )

        self._clock(now_ms)

        duration = memory_exposure_duration(
            question["difficulty"]
        )

        elapsed = now_ms - self.presented_ms

        if elapsed < duration:
            raise SessionStateError(
                "Memory exposure is incomplete."
            )

        self.state = "respond"
        self.response_started_ms = now_ms

        return {
            **self.status(),
            "question": response_question(
                question
            ),
        }

    def _save_outcome(
        self,
        outcome,
        now_ms,
        selected_option_id=None,
        correct=None,
        presented=True,
    ):
        record = self._record()
        question = self._question()

        self.responses.append({
            "item_id": record["item_id"],
            "presentation_id":
                record["presentation_id"],
            "question_id": question["id"],
            "domain": question["domain"],
            "family": question["family"],
            "programmed_difficulty":
                question["difficulty"],
            "block_index": self.block_index,
            "item_index": self.item_index,
            "outcome": outcome,
            "selected_option_id":
                selected_option_id,
            "correct": correct,
            "presented_ms": (
                self.presented_ms
                if presented else None
            ),
            "response_started_ms": (
                self.response_started_ms
                if presented else None
            ),
            "recorded_ms": now_ms,
            "response_latency_ms": (
                now_ms - self.response_started_ms
                if (
                    presented
                    and correct is not None
                    and self.response_started_ms
                    is not None
                )
                else None
            ),
            "calibration_status": "uncalibrated",
        })

    def submit_response(
        self,
        question_id,
        selected_option_id,
        now_ms,
    ):
        self._require_state("respond")

        question = self._question()

        if question_id != question["id"]:
            raise SessionStateError(
                "Stale or unrelated question."
            )

        self._clock(now_ms)

        if self._expired(now_ms):
            self._expire_block(now_ms)
            return self.status()

        evaluation = evaluate_response(
            question,
            selected_option_id,
        )

        correct = evaluation["correct"]

        self._save_outcome(
            "correct" if correct else "incorrect",
            now_ms,
            selected_option_id,
            correct,
        )

        self.state = "answered"

        # No correctness or answer key is
        # returned during an assessment.
        return self.status()

    def advance(self, now_ms):
        self._require_state("answered")
        self._clock(now_ms)

        self.item_index += 1

        block = self._block()

        if self.item_index >= block["item_count"]:
            reason = "fixed_items_completed"

            if block["mode"] == "timed_queue":
                reason = (
                    "queue_exhausted"
                    if not self._expired(now_ms)
                    else "deadline"
                )

            self._finish_block(
                now_ms, reason
            )

            return self.status()

        if self._expired(now_ms):
            self._mark_unreached(now_ms)

            self._finish_block(
                now_ms, "deadline"
            )

            return self.status()

        return self._present(now_ms)

    def _mark_unreached(self, now_ms):
        block = self._block()

        while self.item_index < block["item_count"]:
            self._save_outcome(
                "not_reached",
                now_ms,
                presented=False,
            )

            self.item_index += 1

    def _expire_block(self, now_ms):
        if self.state == "respond":
            self._save_outcome(
                "timed_out",
                now_ms,
            )

            self.item_index += 1

        elif self.state == "answered":
            self.item_index += 1

        else:
            raise SessionStateError(
                "Invalid timed block state."
            )

        self._mark_unreached(now_ms)

        self._finish_block(
            now_ms, "deadline"
        )

    def tick(self, now_ms):
        self._clock(now_ms)

        if (
            self.state in ("respond", "answered")
            and self._expired(now_ms)
        ):
            self._expire_block(now_ms)

        return self.status()

    def _finish_block(self, now_ms, reason):
        block = self._block()

        self.block_results.append({
            "domain": block["domain"],
            "family": block["family"],
            "started_ms":
                self.block_started_ms,
            "deadline_ms":
                self.block_deadline_ms,
            "closed_ms": now_ms,
            "completion_reason": reason,
            "ceiling_limited": (
                reason == "queue_exhausted"
            ),
        })

        self.block_index += 1
        self.item_index = 0

        self.block_started_ms = None
        self.block_deadline_ms = None
        self.presented_ms = None
        self.response_started_ms = None

        if self.block_index == len(self.blocks):
            self.state = "completed"
            self.completed_ms = now_ms

        else:
            self.state = "ready"

    def interrupt(self, reason, now_ms):
        from cognitive_timing import (
            INTERRUPTION_TYPES,
        )

        self._require_state(
            "ready",
            "memorize",
            "respond",
            "answered",
        )

        if reason not in INTERRUPTION_TYPES:
            raise ValueError(
                "Unknown interruption reason."
            )

        self._clock(now_ms)

        self.interruptions.append({
            "reason": reason,
            "recorded_ms": now_ms,
            "previous_state": self.state,
        })

        # Conservative pilot policy:
        # interrupted assessments are retained,
        # but cannot resume or produce results.
        self.state = "interrupted"

        return self.status()

    def results(self):
        self._require_state("completed")

        domains = {}

        for response in self.responses:
            domain = response["domain"]

            if domain not in domains:
                domains[domain] = Counter()

            domains[domain][
                response["outcome"]
            ] += 1

        summaries = {}

        for domain, counts in domains.items():
            correct = counts["correct"]
            incorrect = counts["incorrect"]
            answered = correct + incorrect

            summaries[domain] = {
                "items_answered": answered,
                "correct_responses": correct,
                "incorrect_responses": incorrect,
                "timed_out": counts["timed_out"],
                "not_reached": counts["not_reached"],
                "raw_accuracy": (
                    correct / answered
                    if answered else None
                ),
            }

        return {
            "session_id": self.session_id,
            "form_id": self.form_id,
            "domains": summaries,
            "block_results":
                deepcopy(self.block_results),
            "duration_ms": (
                self.completed_ms - self.created_ms
            ),
            "qualification_status": "experimental",
            "research_only": True,
            "iq_reporting_enabled": False,
            "scientifically_validated": False,
        }


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_rejection(operation):
    try:
        operation()
    except SessionStateError:
        return

    raise AssertionError(
        "Invalid session operation accepted."
    )


def run_tests():
    from cognitive_research_bank import (
        build_research_bank,
    )

    from cognitive_blueprint import (
        assemble_assessment,
    )

    bank = build_research_bank()

    form = assemble_assessment(
        bank, "session-test-v1"
    )

    session = AssessmentSession(
        form, bank, 1000
    )

    require(
        session.state == "ready",
        "Invalid initial state.",
    )

    expect_rejection(
        lambda: session.results()
    )

    expect_rejection(
        lambda: session.advance(1000)
    )

    print("Initial state controls: PASSED")

    now = 1000

    payload = session.begin_block(now)

    question = session._question()

    require(
        "correct_option_id"
        not in payload["question"],
        "Answer key exposed.",
    )

    require(
        "explanation"
        not in payload["question"],
        "Explanation exposed.",
    )

    expect_rejection(
        lambda: session.submit_response(
            "invalid-question", "A", now
        )
    )

    expect_rejection(
        lambda: session.begin_block(now)
    )

    expect_rejection(
        lambda: session.tick(now - 1)
    )

    print("Question identity and clock controls: PASSED")

    now += 1000

    feedback = session.submit_response(
        question["id"],
        question["correct_option_id"],
        now,
    )

    require(
        "correct" not in feedback,
        "Premature correctness feedback.",
    )

    expect_rejection(
        lambda: session.submit_response(
            question["id"],
            question["correct_option_id"],
            now,
        )
    )

    print("Duplicate submission protection: PASSED")
    print("Assessment feedback isolation: PASSED")

    memory_cases = 0
    speed_blocks = 0

    while session.state != "completed":
        if session.state == "ready":
            now += 1000

            payload = session.begin_block(now)

            if session._block()["mode"] == (
                "timed_queue"
            ):
                speed_blocks += 1

                deadline = session.block_deadline_ms

                question = session._question()

                # Accept a response one millisecond
                # before the strict deadline.
                now = deadline - 1

                session.submit_response(
                    question["id"],
                    question["correct_option_id"],
                    now,
                )

                session.advance(now)

                question = session._question()

                # Reject the next response exactly
                # at the deadline.
                now = deadline

                session.submit_response(
                    question["id"],
                    question["correct_option_id"],
                    now,
                )

                continue

        elif session.state == "memorize":
            question = session._question()

            duration = memory_exposure_duration(
                question["difficulty"]
            )

            require(
                "memorize" in payload["question"],
                "Memory stimulus missing.",
            )

            require(
                "options" not in payload["question"],
                "Premature memory answer options.",
            )

            if question["family"] == (
                "sequence_manipulation"
            ):
                require(
                    "response_instruction"
                    in payload["question"],
                    "Manipulation instruction missing.",
                )

            expect_rejection(
                lambda: session.submit_response(
                    question["id"],
                    question["correct_option_id"],
                    now,
                )
            )

            expect_rejection(
                lambda: session.finish_memory_exposure(
                    question["id"],
                    now + duration - 1,
                )
            )

            now += duration

            payload = session.finish_memory_exposure(
                question["id"], now
            )

            require(
                "memorize" not in payload["question"],
                "Memory stimulus remained exposed.",
            )

            memory_cases += 1

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

            payload = session.advance(now)

        else:
            raise AssertionError(
                "Unexpected session state."
            )

    require(
        memory_cases == 12,
        "Incorrect memory item coverage.",
    )

    print("12 controlled memory exposures: PASSED")

    require(
        speed_blocks == 3,
        "Incorrect timed block coverage.",
    )

    counts = Counter(
        response["outcome"]
        for response in session.responses
    )

    require(
        counts["correct"] == 63,
        "Incorrect accepted response count.",
    )

    require(
        counts["timed_out"] == 3,
        "Incorrect timeout count.",
    )

    require(
        counts["not_reached"] == 69,
        "Incorrect unreached count.",
    )

    require(
        len(session.responses) == 135,
        "Incomplete response accounting.",
    )

    print("Strict speed deadline enforcement: PASSED")
    print("135-item outcome accounting: PASSED")

    require(
        len(session.exposures) == 66,
        "Incorrect actual exposure count.",
    )

    print("Actual item exposure tracking: PASSED")

    results = session.results()

    require(
        len(results["domains"]) == 6,
        "Incomplete domain results.",
    )

    require(
        not results["iq_reporting_enabled"]
        and not results["scientifically_validated"],
        "Scientific reporting safeguards failed.",
    )

    expect_rejection(
        lambda: session.begin_block(now)
    )

    print("Assessment completion and results: PASSED")

    interrupted = AssessmentSession(
        form, bank, 1000
    )

    interrupted.begin_block(1000)

    interrupted.interrupt(
        "visibility_lost", 2000
    )

    expect_rejection(
        lambda: interrupted.results()
    )

    expect_rejection(
        lambda: interrupted.advance(2000)
    )

    print("Interrupted assessment isolation: PASSED")

    # Independently test the speed queue ceiling.
    ceiling = AssessmentSession(
        form, bank, 1000
    )

    # Test-only fixture positioning.
    ceiling.block_index = next(
        index
        for index, block in enumerate(
            ceiling.blocks
        )
        if block["mode"] == "timed_queue"
    )

    now = 1000
    ceiling.begin_block(now)

    for _ in range(25):
        question = ceiling._question()

        now += 100

        ceiling.submit_response(
            question["id"],
            question["correct_option_id"],
            now,
        )

        ceiling.advance(now)

    require(
        ceiling.block_results[-1][
            "ceiling_limited"
        ],
        "Speed queue ceiling not detected.",
    )

    print("Speed queue ceiling detection: PASSED")

    print("Scientific reporting safeguards: PASSED")

    print()
    print("ALL ASSESSMENT SESSION TESTS PASSED")


if __name__ == "__main__":
    run_tests()

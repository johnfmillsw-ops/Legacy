import json
import secrets
from uuid import uuid4
from unittest.mock import patch

from database import database_connection

from psycopg.types.json import Jsonb
from werkzeug.security import generate_password_hash


with database_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT current_database() AS name,
                   inet_server_addr()::text AS host
        """)

        db = cur.fetchone()

        if (
            db["name"] != "legacy"
            or db["host"] not in (
                None, "127.0.0.1", "::1"
            )
        ):
            raise RuntimeError("Not the local database.")


# Prevent the background AI worker from starting.
# This patch applies only to this test process.
with patch("personality_service.start_background_service"):
    from webapp import app


app.config["TESTING"] = True

prefix = "/api/personality/baseline"

owner_id = uuid4().hex
other_owner_id = uuid4().hex
profile_id = uuid4().hex
other_profile_id = uuid4().hex

password = secrets.token_urlsafe(24)
password_hash = generate_password_hash(password, method="pbkdf2:sha256:1000000")

email = f"baseline-{owner_id}@example.invalid"
other_email = f"baseline-{other_owner_id}@example.invalid"

client = app.test_client()


def verify(response, expected, label):
    if response.status_code != expected:
        raise AssertionError(
            f"{label}: expected {expected}, "
            f"received {response.status_code}"
        )

    print(label + ": PASSED")

    return response.get_json(silent=True)


def login(email_address):
    client.get("/login")

    with client.session_transaction() as session:
        token = session.get("_csrf_token")

    assert token, "Login CSRF token missing."

    response = client.post(
        "/login",
        data={
            "email": email_address,
            "password": password,
            "_csrf_token": token,
        },
    )

    assert response.status_code == 302

    with client.session_transaction() as session:
        assert session.get("_user_id")

        session["_csrf_token"] = secrets.token_hex(32)


def select_profile(profile):
    with client.session_transaction() as session:
        session["profile_id"] = profile


def post(path, data=None, csrf=True):
    payload = dict(data or {})

    if csrf:
        with client.session_transaction() as session:
            payload["_csrf_token"] = (
                session["_csrf_token"]
            )

    return client.post(prefix + path, data=payload)


print("LEGACY ASSESSMENT API TEST")
print("=" * 50)

try:
    # Create isolated test accounts and profiles.
    with database_connection() as conn:
        with conn.cursor() as cur:

            for uid, address in (
                (owner_id, email),
                (other_owner_id, other_email),
            ):
                cur.execute("""
                    INSERT INTO users (
                        id, email, password_hash,
                        created_utc
                    )
                    VALUES (%s, %s, %s, NOW())
                """, (uid, address, password_hash))

            for pid, uid, consent in (
                (profile_id, owner_id, True),
                (other_profile_id, other_owner_id, False),
            ):
                cur.execute("""
                    INSERT INTO profiles (
                        id, owner_id, display_name,
                        profile_data, created_utc
                    )
                    VALUES (%s, %s, %s, %s, NOW())
                """, (
                    pid,
                    uid,
                    "Temporary API Test",
                    Jsonb({
                        "meta": {
                            "profile_id": pid,
                            "owner_id": uid,
                        },
                        "consent": {
                            "has_consent": consent,
                            "allow_remote_processing": False,
                        },
                        "entries": [],
                    }),
                ))

    verify(
        client.get(prefix + "/instrument"),
        401,
        "Unauthenticated access blocked",
    )

    login(email)

    verify(
        client.get(prefix + "/instrument"),
        403,
        "Missing active profile blocked",
    )

    select_profile(other_profile_id)

    verify(
        client.get(prefix + "/instrument"),
        403,
        "Foreign profile access blocked",
    )

    select_profile(profile_id)

    instrument = verify(
        client.get(prefix + "/instrument"),
        200,
        "Authorized instrument retrieval",
    )

    assert len(instrument["questions"]) == 50

    assert all(
        set(question) == {"id", "text"}
        for question in instrument["questions"]
    )

    print("Scoring key protection: PASSED")

    verify(
        post("/start", csrf=False),
        403,
        "Missing CSRF token blocked",
    )

    verify(
        client.post(
            prefix + "/start",
            data={"_csrf_token": "invalid"},
        ),
        403,
        "Invalid CSRF token blocked",
    )

    result = verify(
        post("/start"),
        200,
        "Assessment creation",
    )

    assessment_id = result["assessment"]["id"]

    resumed = verify(
        post("/start"),
        200,
        "Assessment resumption",
    )

    assert resumed["assessment"]["id"] == assessment_id

    verify(
        post(f"/{assessment_id}/save", {
            "responses": "{invalid json"
        }),
        400,
        "Malformed JSON blocked",
    )

    verify(
        post(f"/{assessment_id}/save", {
            "responses": json.dumps({"1": 6})
        }),
        400,
        "Invalid response blocked",
    )

    result = verify(
        post(f"/{assessment_id}/save", {
            "responses": json.dumps({"1": 3})
        }),
        200,
        "Partial progress saved",
    )

    assert result["assessment"]["answered_count"] == 1

    verify(
        post(f"/{assessment_id}/complete"),
        400,
        "Incomplete submission blocked",
    )

    result = verify(
        post(f"/{assessment_id}/save", {
            "responses": json.dumps({
                str(i): 3
                for i in range(2, 51)
            })
        }),
        200,
        "Remaining responses saved",
    )

    assert result["assessment"]["answered_count"] == 50

    result = verify(
        post(f"/{assessment_id}/complete"),
        200,
        "Assessment completion",
    )

    assert result["assessment"]["status"] == "completed"

    scores = result["assessment"]["normalized_scores"]

    assert len(scores) == 5
    assert all(value == 50 for value in scores.values())

    print("API scoring accuracy: PASSED")

    latest = verify(
        client.get(prefix + "/latest"),
        200,
        "Latest baseline retrieval",
    )

    assert latest["assessment"]["id"] == assessment_id

    history = verify(
        client.get(prefix + "/history"),
        200,
        "Assessment history retrieval",
    )

    assert len(history["assessments"]) == 1

    verify(
        post(f"/{assessment_id}/save", {
            "responses": json.dumps({"1": 5})
        }),
        400,
        "Completed assessment modification blocked",
    )

    verify(
        post(f"/{assessment_id}/complete"),
        400,
        "Duplicate completion blocked",
    )

    with client.session_transaction() as session:
        session.clear()

    login(other_email)
    select_profile(other_profile_id)

    verify(
        client.get(prefix + "/instrument"),
        403,
        "Missing consent blocked",
    )

    # Enable consent for the isolated second test profile.
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE profiles
                SET profile_data = jsonb_set(
                    profile_data,
                    '{consent,has_consent}',
                    'true'::jsonb
                )
                WHERE id = %s
                  AND owner_id = %s
            """, (other_profile_id, other_owner_id))

    verify(
        post(f"/{assessment_id}/save", {
            "responses": json.dumps({"1": 5})
        }),
        400,
        "Cross-profile assessment modification blocked",
    )

    verify(
        post(f"/{assessment_id}/complete"),
        400,
        "Cross-profile completion blocked",
    )

    history = verify(
        client.get(prefix + "/history"),
        200,
        "Independent profile history",
    )

    assert history["assessments"] == []

    latest = verify(
        client.get(prefix + "/latest"),
        200,
        "Independent profile baseline",
    )

    assert latest["assessment"] is None

finally:
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM personality_baseline_assessments
                WHERE profile_id IN (%s, %s)
            """, (profile_id, other_profile_id))

            print("\nTest assessments removed:", cur.rowcount)

            cur.execute("""
                DELETE FROM profiles
                WHERE id IN (%s, %s)
            """, (profile_id, other_profile_id))

            print("Test profiles removed:", cur.rowcount)

            cur.execute("""
                DELETE FROM users
                WHERE id IN (%s, %s)
            """, (owner_id, other_owner_id))

            print("Test accounts removed:", cur.rowcount)

print("\nAll assessment API tests passed.")
print("Existing user data preserved.")
print("Background personality worker not started.")
print("No external AI requests.")

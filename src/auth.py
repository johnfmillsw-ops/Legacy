
from __future__ import annotations

import re
import psycopg
import secrets

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
)

from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from database import (
    create_user,
    get_user_by_id,
    get_user_by_email,
)


# --------------------------------------------------
# Authentication configuration
# --------------------------------------------------

auth = Blueprint("auth", __name__)

login_manager = LoginManager()

login_manager.login_view = "auth.login"

login_manager.login_message = (
    "Please log in to access Legacy."
)

login_manager.session_protection = "strong"


# --------------------------------------------------
# User model
# --------------------------------------------------

class User(UserMixin):

    def __init__(self, record):
        self.id = record["id"]
        self.email = record["email"]
        self.created_utc = record["created_utc"]


@login_manager.user_loader
def load_user(user_id):

    record = get_user_by_id(user_id)

    if record is None:
        return None

    return User(record)


# --------------------------------------------------
# Initialization
# --------------------------------------------------

def initialize_auth(app):

    login_manager.init_app(app)

    app.register_blueprint(auth)

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
    )


# --------------------------------------------------
# CSRF protection
# --------------------------------------------------

def csrf_token():

    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)

    return session["_csrf_token"]


@auth.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@auth.before_request
def verify_csrf_token():

    if request.method == "POST":

        expected = session.get("_csrf_token", "")
        provided = request.form.get("_csrf_token", "")

        if not expected or not secrets.compare_digest(
            expected,
            provided,
        ):
            abort(403)


# --------------------------------------------------
# Input validation
# --------------------------------------------------

def valid_email(email):

    if len(email) > 254:
        return False

    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email,
        )
    )


# --------------------------------------------------
# Registration
# --------------------------------------------------

@auth.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":

        email = (
            request.form.get("email") or ""
        ).strip().lower()

        password = (
            request.form.get("password") or ""
        )

        confirm_password = (
            request.form.get("confirm_password") or ""
        )

        if not valid_email(email):

            flash("Enter a valid email address.")

            return render_template("register.html")

        if len(password) < 12:

            flash(
                "Password must contain at least "
                "12 characters."
            )

            return render_template("register.html")

        if len(password) > 128:

            flash("Password is too long.")

            return render_template("register.html")

        if password != confirm_password:

            flash("Passwords do not match.")

            return render_template("register.html")

        if get_user_by_email(email):

            flash(
                "Unable to register with this email."
            )

            return render_template("register.html")

        password_hash = generate_password_hash(
            password,
            method="pbkdf2:sha256:1000000",
        )

        try:

            record = create_user(
                email,
                password_hash,
            )

        except psycopg.errors.UniqueViolation:

            flash(
                "Unable to register with this email."
            )

            return render_template("register.html")

        session.clear()

        login_user(User(record))

        flash("Your Legacy account has been created.")

        return redirect(url_for("index"))

    return render_template("register.html")


# --------------------------------------------------
# Login
# --------------------------------------------------

@auth.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":

        email = (
            request.form.get("email") or ""
        ).strip().lower()

        password = (
            request.form.get("password") or ""
        )

        if not valid_email(email) or len(password) > 128:

            flash("Invalid email or password.")

            return render_template("login.html")

        record = get_user_by_email(email)

        if record is None or not check_password_hash(
            record["password_hash"],
            password,
        ):

            flash("Invalid email or password.")

            return render_template("login.html")

        session.clear()

        login_user(User(record))

        flash("Welcome back to Legacy.")

        return redirect(url_for("index"))

    return render_template("login.html")


# --------------------------------------------------
# Logout
# --------------------------------------------------

@auth.route("/logout", methods=["POST"])
@login_required
def logout():

    logout_user()

    session.clear()

    flash("You have been logged out.")

    return redirect(url_for("auth.login"))

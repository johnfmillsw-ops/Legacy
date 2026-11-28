from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings

from flask import (
    Blueprint,
    jsonify,
    request,
    session,
    send_file,
    url_for,
)

from flask_login import login_required, current_user

from PIL import Image, ImageOps, UnidentifiedImageError

from database import database_connection

from psycopg.errors import UniqueViolation
from archive_photo_storage import optimized_copies, quota_bytes
from archive_photo_import import decode_upload


gallery_bp = Blueprint(
    "archive_gallery",
    __name__,
    url_prefix="/api/archive/gallery",
)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

IMAGE_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def authorized_profile():

    profile_id = session.get("profile_id")

    if not profile_id:
        return None

    with database_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT id
                FROM profiles
                WHERE id = %s
                  AND owner_id = %s
                """,
                (profile_id, current_user.id),
            )

            record = cursor.fetchone()

    return record["id"] if record else None


def serialize_asset(record):

    result = dict(record)

    for key, value in result.items():

        if hasattr(value, "isoformat"):
            result[key] = value.isoformat()

    result["thumbnail_url"] = url_for(
        "archive_gallery.thumbnail",
        asset_id=result["id"],
    )

    result["image_url"] = url_for(
        "archive_gallery.original",
        asset_id=result["id"],
    )

    return result


def field(name, maximum, required=False):

    value = request.form.get(name, "").strip()

    if required and not value:
        raise ValueError(f"{name.title()} is required.")

    if len(value) > maximum:
        raise ValueError(
            f"{name.title()} exceeds {maximum} characters."
        )

    return value


def validate_event_date(value):

    if not value:
        return ""

    try:

        if len(value) == 4:
            date(int(value), 1, 1)

        elif len(value) == 7:
            date.fromisoformat(value + "-01")

        elif len(value) == 10:
            date.fromisoformat(value)

        else:
            raise ValueError

    except ValueError:
        raise ValueError(
            "Use YYYY, YYYY-MM or YYYY-MM-DD for the event date."
        )

    return value


def prepare_image(data):

    if not data:
        raise ValueError("The photograph is empty.")

    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Photographs cannot exceed 15 MB.")

    try:

        with warnings.catch_warnings():

            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning,
            )

            with Image.open(BytesIO(data)) as image:

                image_format = image.format

                if image_format not in IMAGE_TYPES:
                    raise ValueError(
                        "Use a JPEG, PNG or WebP photograph."
                    )

                width, height = image.size

                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError(
                        "Photographs cannot exceed 40 megapixels."
                    )

                if getattr(image, "is_animated", False):
                    raise ValueError(
                        "Animated images are not supported."
                    )

                image.verify()

            with Image.open(BytesIO(data)) as image:

                image = ImageOps.exif_transpose(image)

                image.thumbnail((1000, 1000))

                if image.mode in ("RGBA", "LA"):

                    rgba = image.convert("RGBA")

                    background = Image.new(
                        "RGB",
                        rgba.size,
                        "#211e18",
                    )

                    background.paste(
                        rgba,
                        mask=rgba.getchannel("A"),
                    )

                    image = background

                else:
                    image = image.convert("RGB")

                output = BytesIO()

                image.save(
                    output,
                    format="JPEG",
                    quality=85,
                    optimize=True,
                )

    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValueError(
            "The uploaded file is not a valid photograph."
        )

    return IMAGE_TYPES[image_format], output.getvalue()


@gallery_bp.get("")
@login_required
def gallery():

    profile_id = authorized_profile()

    if not profile_id:
        return jsonify({"error": "Access denied."}), 403

    with database_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    a.id,
                    a.title,
                    a.description,
                    a.event_date,
                    a.location,
                    a.people,
                    a.original_filename,
                    a.mime_type,
                    a.file_size_bytes,
                    a.preservation_mode,
                    a.created_utc
                FROM archive_assets a
                JOIN profiles p ON p.id = a.profile_id
                WHERE a.profile_id = %s
                  AND p.owner_id = %s
                ORDER BY a.created_utc DESC
                """,
                (profile_id, current_user.id),
            )

            assets = [
                serialize_asset(record)
                for record in cursor.fetchall()
            ]

    return jsonify({"assets": assets})


@gallery_bp.post("")
@login_required
def upload():

    profile_id = authorized_profile()

    if not profile_id:
        return jsonify({"error": "Access denied."}), 403

    file = request.files.get("photo")

    if file is None or not file.filename:
        return jsonify({"error": "Select a photograph."}), 400

    try:

        title = field("title", 200, required=True)
        description = field("description", 10000)
        event_date = validate_event_date(
            field("event_date", 10)
        )
        location = field("location", 300)
        people = field("people", 1000)

        data = file.stream.read(MAX_IMAGE_BYTES + 1)

        mime_type, image_data, page_number = decode_upload(data, request.form.get("pdf_page", "1"))
        prepare_image(image_data)
        mode = request.form.get("preservation_mode", "standard")
        if mode not in ("standard", "original"):
            raise ValueError("Invalid preservation option.")
        optimized, thumbnail_data = optimized_copies(image_data)
        stored = data if mode == "original" else optimized
        display = optimized if mode == "original" else None
        if mode == "standard":
            mime_type = "image/webp"

        content_hash = sha256(data if page_number is None else data + b"\0legacy-pdf-page:" + str(page_number).encode()).hexdigest()

        asset_id = uuid4().hex

        filename = Path(file.filename).name[:255]
        if page_number is not None and mode == "standard":
            filename = Path(filename).stem[:230] + f"-page-{page_number}.webp"

        with database_connection() as connection:
            with connection.cursor() as cursor:

                cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("archive-photo:" + str(current_user.id),))
                cursor.execute("""
                    SELECT COALESCE(SUM(octet_length(a.original_data)::bigint + octet_length(a.thumbnail_data) + COALESCE(octet_length(a.display_data), 0)), 0) AS used
                    FROM archive_assets a JOIN profiles p ON p.id = a.profile_id
                    WHERE p.owner_id = %s
                """, (current_user.id,))
                used = cursor.fetchone()["used"]
                if used + len(stored) + len(thumbnail_data) + len(display or b"") > quota_bytes():
                    return jsonify({"error": "Account photograph storage allowance reached."}), 413
                cursor.execute(
                    """
                    INSERT INTO archive_assets (
                        id,
                        profile_id,
                        title,
                        description,
                        event_date,
                        location,
                        people,
                        original_filename,
                        mime_type,
                        file_size_bytes,
                        content_hash,
                        original_data,
                        thumbnail_data, preservation_mode, display_data, thumbnail_mime
                    )
                    SELECT
                        %s, p.id, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    FROM profiles p
                    WHERE p.id = %s
                      AND p.owner_id = %s
                    RETURNING id
                    """,
                    (
                        asset_id,
                        title,
                        description,
                        event_date,
                        location,
                        people,
                        filename,
                        mime_type,
                        len(stored),
                        content_hash,
                        stored,
                        thumbnail_data,
                        mode,
                        display,
                        "image/webp",
                        profile_id,
                        current_user.id,
                    ),
                )

                if cursor.fetchone() is None:
                    return jsonify({
                        "error": "Access denied."
                    }), 403

    except UniqueViolation:

        return jsonify({
            "error": "This exact photograph is already preserved."
        }), 409

    except ValueError as error:

        return jsonify({
            "error": str(error)
        }), 400

    return jsonify({
        "success": True,
        "id": asset_id,
    }), 201


def retrieve_image(asset_id, use_thumbnail=False):

    profile_id = authorized_profile()

    if not profile_id:
        return jsonify({"error": "Access denied."}), 403

    column = (
        "thumbnail_data"
        if use_thumbnail
        else ("original_data" if request.args.get("download") == "1" else "display_data")
    )

    with database_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                f"""
                SELECT
                    COALESCE(a.{column}, a.original_data) AS image_data,
                    a.thumbnail_mime,
                    a.preservation_mode,
                    (a.display_data IS NOT NULL) AS has_display,
                    a.mime_type,
                    a.original_filename
                FROM archive_assets a
                JOIN profiles p ON p.id = a.profile_id
                WHERE a.id = %s
                  AND a.profile_id = %s
                  AND p.owner_id = %s
                """,
                (asset_id, profile_id, current_user.id),
            )

            record = cursor.fetchone()

    if record is None:
        return jsonify({"error": "Photograph not found."}), 404

    response = send_file(
        BytesIO(bytes(record["image_data"])),
        mimetype=(
            record["thumbnail_mime"]
            if use_thumbnail
            else ("image/webp" if column == "display_data" and record["has_display"] else record["mime_type"])
        ),
        download_name=(
            ("thumbnail.webp" if record["thumbnail_mime"] == "image/webp" else "thumbnail.jpg")
            if use_thumbnail
            else (Path(record["original_filename"]).stem + ".webp" if record["preservation_mode"] == "standard" or (column == "display_data" and record["has_display"]) else record["original_filename"])
        ),
        as_attachment=(
            not use_thumbnail
            and request.args.get("download") == "1"
        ),
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@gallery_bp.get("/<asset_id>/thumbnail")
@login_required
def thumbnail(asset_id):
    return retrieve_image(asset_id, use_thumbnail=True)


@gallery_bp.get("/<asset_id>/original")
@login_required
def original(asset_id):
    return retrieve_image(asset_id)


@gallery_bp.post('/<asset_id>/edit')
@login_required
def edit_photo(asset_id):
    profile_id = authorized_profile()
    if not profile_id:
        return jsonify(error='Access denied.'), 403
    try:
        values = (field('title', 200, required=True), field('description', 10000),
                  validate_event_date(field('event_date', 10)), field('location', 300), field('people', 1000))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''UPDATE archive_assets a SET title=%s, description=%s,
                event_date=%s, location=%s, people=%s, updated_utc=NOW()
                FROM profiles p WHERE a.id=%s AND a.profile_id=%s AND p.id=a.profile_id
                AND p.owner_id=%s RETURNING a.id, a.title, a.description, a.event_date,
                a.location, a.people, a.original_filename, a.mime_type, a.file_size_bytes,
                a.preservation_mode, a.created_utc''', (*values, asset_id, profile_id, current_user.id))
            record = cursor.fetchone()
            if not record:
                return jsonify(error='Photograph not found.'), 404
            cursor.execute("DELETE FROM archive_relationships WHERE profile_id=%s AND asset_id=%s AND status='suggested'", (profile_id, asset_id))
    return jsonify(asset=serialize_asset(record))


@gallery_bp.post('/<asset_id>/delete')
@login_required
def delete_photo(asset_id):
    profile_id = authorized_profile()
    if not profile_id:
        return jsonify(error='Access denied.'), 403
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''DELETE FROM archive_assets a USING profiles p
                WHERE a.id=%s AND a.profile_id=%s AND p.id=a.profile_id AND p.owner_id=%s
                RETURNING a.id''', (asset_id, profile_id, current_user.id))
            if not cursor.fetchone():
                return jsonify(error='Photograph not found.'), 404
    return jsonify(deleted=True)

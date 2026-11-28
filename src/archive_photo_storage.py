import os
from io import BytesIO
from PIL import Image, ImageOps


def quota_bytes():
    return int(os.environ.get('LEGACY_PHOTO_QUOTA_BYTES', '1000000000'))


def encode(image, edge, quality, limit):
    image = image.copy()
    image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    while True:
        out = BytesIO()
        image.save(out, 'WEBP', quality=quality, method=4)
        data = out.getvalue()
        if len(data) <= limit:
            return data
        if quality > 55:
            quality -= 10
        else:
            image.thumbnail(tuple(max(1, int(n * .8)) for n in image.size), Image.Resampling.LANCZOS)


def optimized_copies(data):
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source)
        image = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
        return encode(image, 2560, 85, 600000), encode(image, 400, 78, 60000)

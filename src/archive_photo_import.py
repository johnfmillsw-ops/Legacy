from io import BytesIO
from contextlib import closing
from PIL import Image, ImageOps

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000

def decode_upload(data, page='1'):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Select a nonempty file no larger than 15 MB.')
    if data.startswith(b'%PDF-'):
        import pypdfium2 as pdfium
        try:
            number = int(page)
            with pdfium.PdfDocument(data) as doc:
                if not 1 <= number <= len(doc):
                    raise ValueError(f'Choose a PDF page from 1 to {len(doc)}.')
                with closing(doc[number - 1]) as sheet:
                    w, h = sheet.get_size()
                    if min(w,h) <= 0:
                        raise ValueError('Invalid PDF page dimensions.')
                    with closing(sheet.render(scale=min(3, 2560/max(w,h)))) as bitmap:
                        out = BytesIO()
                        bitmap.to_pil().convert('RGB').save(out, 'PNG')
                        return 'application/pdf', out.getvalue(), number
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('Unable to read PDF. Check whether it is encrypted or damaged.') from exc
    if len(data) >= 12 and data[4:8] == b'ftyp':
        try:
            from pillow_heif import open_heif
            source = open_heif(data, convert_hdr_to_8bit=True)
            if source.size[0]*source.size[1] > MAX_PIXELS:
                raise ValueError('Photographs cannot exceed 40 megapixels.')
            if len(source) != 1:
                raise ValueError('Choose a single-image HEIC or HEIF file.')
            image = ImageOps.exif_transpose(source.to_pillow())
            image.thumbnail((2560,2560))
            out = BytesIO()
            image.convert('RGB').save(out,'PNG')
            return 'image/heic', out.getvalue(), None
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('Unable to read HEIC or HEIF photograph.') from exc
    try:
        with Image.open(BytesIO(data)) as image:
            mime = {'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}.get(image.format)
            if not mime:
                raise ValueError('Unsupported photograph format.')
            return mime, data, None
    except OSError as exc:
        raise ValueError('Invalid photograph.') from exc

"""
pdf_utils.py — Aggressive PDF compression before Dropbox upload.

Compression pipeline (best result wins):

  Stage 1 — pikepdf structural (lossless)
             Strips dead objects, recompresses streams, normalises xref.
             Typical saving: 5-20 % on most PDFs.

  Stage 2 — pikepdf + Pillow image recompression  ← NEW main workhorse
             Opens every embedded image with Pillow and re-encodes:
               • JPEG/RGB  → JPEG quality=72, subsampling=2x2
               • RGBA/P    → PNG  compression=9
               • Grayscale → JPEG quality=72
             Then saves via pikepdf with all Stage-1 options enabled.
             Typical saving: 40-75 % on scan/image-heavy PDFs.

  Stage 3 — pypdf zlib fallback
             Pure-Python rewrite with compress_content_streams(level=9).
             Useful when pikepdf is missing or fails.

  Stage 4 — passthrough
             Returns original bytes unchanged so the upload always succeeds.

Only a result that is at least 3 % smaller than the original is accepted
for a given stage; otherwise the next stage is tried.
"""

import io
import logging

logger = logging.getLogger(__name__)

# Minimum saving threshold: only accept compressed result if it beats
# the current best by at least this fraction.
_MIN_SAVING_RATIO = 0.97   # i.e. must be < 97 % of current best size


# ─── Stage 1: pikepdf structural (lossless) ──────────────────────────────────

def _compress_pikepdf_structural(data: bytes) -> bytes:
    """Lossless structural recompression via pikepdf/libqpdf."""
    import pikepdf

    with pikepdf.open(io.BytesIO(data)) as pdf:
        pdf.remove_unreferenced_resources()
        out = io.BytesIO()
        pdf.save(
            out,
            compress_streams=True,
            stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            normalise_content=True,
            linearize=False,
        )
        return out.getvalue()


# ─── Stage 2: pikepdf + Pillow image recompression ───────────────────────────

def _recompress_image_xobject(image_obj, jpeg_quality: int = 72) -> bool:
    """
    Re-encode a single PDF image XObject in-place using Pillow.
    Returns True if the object was successfully replaced.
    """
    import pikepdf
    from PIL import Image

    try:
        pil_img = image_obj.as_pil_image()
    except Exception:
        return False

    buf = io.BytesIO()
    mode = pil_img.mode

    try:
        if mode in ('RGBA', 'P', 'LA'):
            pil_img = pil_img.convert('RGBA')
            pil_img.save(buf, format='PNG', optimize=True, compress_level=9)
            buf.seek(0)
            compressed_bytes = buf.read()
            new_obj = pikepdf.Stream(
                image_obj.owner,
                compressed_bytes,
            )
            new_obj['/Filter'] = pikepdf.Name('/FlateDecode')
        else:
            if mode not in ('RGB', 'L'):
                pil_img = pil_img.convert('RGB')
            pil_img.save(
                buf, format='JPEG',
                quality=jpeg_quality,
                optimize=True,
                subsampling=2,   # 2×2 chroma subsampling (4:2:0)
            )
            buf.seek(0)
            compressed_bytes = buf.read()
            new_obj = pikepdf.Stream(
                image_obj.owner,
                compressed_bytes,
            )
            new_obj['/Filter'] = pikepdf.Name('/DCTDecode')

        orig_w = int(image_obj['/Width'])
        orig_h = int(image_obj['/Height'])
        new_obj['/Type']    = pikepdf.Name('/XObject')
        new_obj['/Subtype'] = pikepdf.Name('/Image')
        new_obj['/Width']   = orig_w
        new_obj['/Height']  = orig_h
        if mode in ('RGBA', 'P', 'LA'):
            new_obj['/ColorSpace'] = pikepdf.Name('/DeviceRGB')
            new_obj['/BitsPerComponent'] = 8
        elif mode == 'L':
            new_obj['/ColorSpace'] = pikepdf.Name('/DeviceGray')
            new_obj['/BitsPerComponent'] = 8
        else:
            new_obj['/ColorSpace'] = pikepdf.Name('/DeviceRGB')
            new_obj['/BitsPerComponent'] = 8

        image_obj.stream_dict.update(new_obj.stream_dict)
        image_obj.write(
            pikepdf.compress(b'', pikepdf.Compression.deflate) if False else compressed_bytes,
            filter=new_obj.get('/Filter'),
        )
        return True

    except Exception as exc:
        logger.debug('pdf_utils: image recompress skipped: %s', exc)
        return False


def _compress_pikepdf_with_images(data: bytes, jpeg_quality: int = 72) -> bytes:
    """
    Re-encode all embedded images then save with full structural compression.
    """
    import pikepdf
    from pikepdf import PdfImage

    with pikepdf.open(io.BytesIO(data)) as pdf:
        pdf.remove_unreferenced_resources()

        # Walk every page's resource dictionary for image XObjects
        for page in pdf.pages:
            try:
                resources = page.get('/Resources', {})
                xobjects  = resources.get('/XObject', {})
            except Exception:
                continue

            for key in list(xobjects.keys()):
                try:
                    obj = xobjects[key]
                    if obj.get('/Subtype') == '/Image':
                        try:
                            pil_img = PdfImage(obj).as_pil_image()
                        except Exception:
                            continue

                        mode = pil_img.mode
                        buf  = io.BytesIO()

                        if mode in ('RGBA', 'P', 'LA'):
                            pil_img = pil_img.convert('RGBA')
                            pil_img.save(buf, format='PNG', optimize=True, compress_level=9)
                            new_filter = pikepdf.Name('/FlateDecode')
                            new_cs     = pikepdf.Name('/DeviceRGB')
                            bits       = 8
                        else:
                            if mode not in ('RGB', 'L'):
                                pil_img = pil_img.convert('RGB')
                            pil_img.save(
                                buf, format='JPEG',
                                quality=jpeg_quality,
                                optimize=True,
                                subsampling=2,
                            )
                            new_filter = pikepdf.Name('/DCTDecode')
                            new_cs     = (pikepdf.Name('/DeviceGray')
                                          if pil_img.mode == 'L'
                                          else pikepdf.Name('/DeviceRGB'))
                            bits = 8

                        buf.seek(0)
                        raw = buf.read()

                        obj.write(raw, filter=new_filter)
                        obj['/ColorSpace'] = new_cs
                        obj['/BitsPerComponent'] = bits
                        # Remove any stale decode params
                        for key_to_del in ('/DecodeParms', '/SMask', '/Mask'):
                            try:
                                del obj[key_to_del]
                            except Exception:
                                pass

                except Exception as exc:
                    logger.debug('pdf_utils: skipped XObject: %s', exc)
                    continue

        out = io.BytesIO()
        pdf.save(
            out,
            compress_streams=True,
            stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            normalise_content=True,
            linearize=False,
        )
        return out.getvalue()


# ─── Stage 3: pypdf zlib fallback ────────────────────────────────────────────

def _compress_with_pypdf(data: bytes) -> bytes:
    """Use pypdf to rewrite the PDF with maximum zlib compression."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    for page in writer.pages:
        try:
            page.compress_content_streams(level=9)
        except TypeError:
            page.compress_content_streams()

    try:
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    except AttributeError:
        pass

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ─── Public API ───────────────────────────────────────────────────────────────

def compress_pdf(file_obj) -> tuple:
    """
    Read *file_obj* (a Django UploadedFile or any file-like with .read()),
    compress it through a 3-stage pipeline, and return:

        (best_bytes, original_size, best_size, method_used)

    Stages run in order; a stage's result is accepted only if it is
    strictly smaller than the current best.  The function never raises.
    """
    file_obj.seek(0)
    original_data = file_obj.read()
    original_size = len(original_data)
    best_data     = original_data
    best_size     = original_size
    best_method   = 'passthrough'

    def _accept(new_data: bytes, method: str) -> bool:
        nonlocal best_data, best_size, best_method
        if len(new_data) < best_size * _MIN_SAVING_RATIO:
            best_data   = new_data
            best_size   = len(new_data)
            best_method = method
            return True
        return False

    # ── Stage 1: lossless structural ─────────────────────────────────────────
    try:
        _accept(_compress_pikepdf_structural(original_data), 'pikepdf-structural')
    except ImportError:
        logger.info('pdf_utils: pikepdf not installed')
    except Exception as exc:
        logger.warning('pdf_utils: stage1 failed: %s', exc)

    # ── Stage 2: image recompression (biggest wins on scan PDFs) ─────────────
    try:
        compressed = _compress_pikepdf_with_images(original_data, jpeg_quality=72)
        _accept(compressed, 'pikepdf+images')
    except ImportError as exc:
        logger.info('pdf_utils: stage2 skipped (missing lib: %s)', exc)
    except Exception as exc:
        logger.warning('pdf_utils: stage2 failed: %s', exc)

    # ── Stage 3: pypdf zlib fallback ─────────────────────────────────────────
    try:
        compressed = _compress_with_pypdf(original_data)
        _accept(compressed, 'pypdf')
    except ImportError:
        logger.info('pdf_utils: pypdf not installed')
    except Exception as exc:
        logger.warning('pdf_utils: stage3 failed: %s', exc)

    return best_data, original_size, best_size, best_method


def human_size(n_bytes: int) -> str:
    """Return a human-readable file size string, e.g. '45.2\u00a0MB'."""
    n = float(n_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f}\u00a0{unit}'
        n /= 1024
    return f'{n:.1f}\u00a0TB'

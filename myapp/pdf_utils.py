"""
pdf_utils.py — Lossless PDF compression before Dropbox upload.

Strategy (in order of preference):
  1. pikepdf  — strips dead objects, compresses streams, normalises xref
               tables, removes unreferenced resources.  Typically achieves
               20-60 % reduction on real-world PDFs.
  2. pypdf    — pure-Python fallback; recompresses content streams with
               zlib level 9.  Lighter savings (~5-20 %) but zero system
               dependencies beyond the pip package.
  3. passthrough — if both fail, returns the original bytes unchanged so the
               upload always continues.

All compression is *lossless*: text, vector graphics, and already-compressed
images are never re-encoded or degraded.
"""

import io
import logging

logger = logging.getLogger(__name__)


def _compress_with_pikepdf(data: bytes) -> bytes:
    """Use pikepdf (libqpdf) to recompress and normalise the PDF."""
    import pikepdf

    with pikepdf.open(io.BytesIO(data)) as pdf:
        # Remove dead/unreferenced objects before saving
        pdf.remove_unreferenced_resources()

        out = io.BytesIO()
        pdf.save(
            out,
            compress_streams=True,
            stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            normalise_content=True,   # canonicalise content streams
            linearize=False,
        )
        return out.getvalue()


def _compress_with_pypdf(data: bytes) -> bytes:
    """Use pypdf to rewrite the PDF with maximum zlib compression."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    # Max-level deflate on every content stream
    for page in writer.pages:
        for filt in getattr(page, 'compress_content_streams', [None]):
            break
        try:
            page.compress_content_streams(level=9)
        except TypeError:
            page.compress_content_streams()   # older pypdf without level= kwarg

    # Deduplicate identical indirect objects (images, fonts shared across pages)
    try:
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    except AttributeError:
        pass   # older pypdf versions don't have this method

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def compress_pdf(file_obj) -> tuple[bytes, int, int, str]:
    """
    Read *file_obj* (a Django UploadedFile or any file-like with .read()),
    compress it, and return:

        (compressed_bytes, original_size_bytes, compressed_size_bytes, method_used)

    *method_used* is one of 'pikepdf', 'pypdf', or 'passthrough'.
    The function never raises — failures fall through to the next strategy.
    """
    file_obj.seek(0)
    original_data = file_obj.read()
    original_size = len(original_data)
    best_data     = original_data
    best_size     = original_size
    best_method   = 'passthrough'

    # ── 1. Try pikepdf ────────────────────────────────────────────────────────
    try:
        compressed = _compress_with_pikepdf(original_data)
        if len(compressed) < best_size:
            best_data   = compressed
            best_size   = len(compressed)
            best_method = 'pikepdf'
    except ImportError:
        logger.info('pdf_utils: pikepdf not available, trying pypdf')
    except Exception as exc:
        logger.warning('pdf_utils: pikepdf failed (%s), trying pypdf', exc)

    # ── 2. Try pypdf (always run — may beat pikepdf on some files) ────────────
    try:
        compressed = _compress_with_pypdf(original_data)
        if len(compressed) < best_size:
            best_data   = compressed
            best_size   = len(compressed)
            best_method = 'pypdf'
    except ImportError:
        logger.info('pdf_utils: pypdf not available')
    except Exception as exc:
        logger.warning('pdf_utils: pypdf failed (%s)', exc)

    return best_data, original_size, best_size, best_method


def human_size(n_bytes: int) -> str:
    """Return a human-readable file size string, e.g. '45.2 MB'."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n_bytes < 1024:
            return f'{n_bytes:.1f} {unit}'
        n_bytes /= 1024
    return f'{n_bytes:.1f} TB'

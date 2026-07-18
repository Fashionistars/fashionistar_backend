# apps/measurements/services/qr_service.py
"""
QR Code generation service for FASHIONISTAR AI Body Scan sessions.

Responsibilities:
  1. generate_measurement_url(session_id) → the canonical frontend scan URL
  2. generate_qr_code_b64(url)            → brand-styled base64 PNG QR code
  3. upload_qr_to_cloudinary(b64, id)     → persists QR to Cloudinary storage

Architecture Notes:
  - QR codes use ERROR_CORRECT_H (30% redundancy) to allow future logo overlay.
  - Brand colours: Forest Green (#2D6A4F) modules on near-black (#0A0A0A) background.
  - Cloudinary upload is called from a Celery task (non-blocking on request path).
  - If Cloudinary upload fails, the function returns "" (graceful degradation).
    The frontend uses qr_code_b64 from the response for immediate display;
    qr_code_url is only used for long-term retrieval/audit.

FASHIONISTAR Brand Compliance:
  - Forest Green   #2D6A4F  → QR modules
  - Near-black     #0A0A0A  → QR background
  - Golden Yellow  #F4C430  → reserved for logo overlay (future)

Usage (from InitiateScanView):
    url   = generate_measurement_url(str(session.session_id))
    b64   = generate_qr_code_b64(url)
    # url + b64 returned immediately in API response
    # Cloudinary upload happens async via Celery (upload_qr_code_to_cloudinary task)
"""

from __future__ import annotations

import base64
import io
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Brand constants ──────────────────────────────────────────────────────────

BRAND_GREEN  = "#2D6A4F"   # Forest Green — QR modules
BRAND_BLACK  = "#0A0A0A"   # Near-black   — QR background
QR_BOX_SIZE  = 10          # Pixels per QR module
QR_BORDER    = 2           # Quiet-zone border modules


# ─── URL Generation ───────────────────────────────────────────────────────────

def generate_measurement_url(session_id: str) -> str:
    """
    Build the canonical frontend URL for a scan session.

    Format:  {FRONTEND_URL}/scan/{session_id}

    Settings:
      FRONTEND_URL: configurable in Django settings / env.
      Defaults to "https://fashionistar.net" if not set.

    Args:
        session_id: String UUID of the BodyScanSession.

    Returns:
        Absolute URL string, e.g.:
        "https://fashionistar.net/scan/3fa85f64-5717-4562-b3fc-2c963f66afa6"
    """
    frontend_url = getattr(settings, "FRONTEND_URL", "https://fashionistar.net").rstrip("/")
    return f"{frontend_url}/scan/{session_id}"


# ─── QR Code Generation ───────────────────────────────────────────────────────

def generate_qr_code_b64(url: str) -> str:
    """
    Generate a brand-styled QR code PNG and return it as a base64 string.

    Styling:
      - Module colour: BRAND_GREEN (#2D6A4F)
      - Background:    BRAND_BLACK (#0A0A0A)
      - Rounded module drawer (softer aesthetic)
      - Error correction: ERROR_CORRECT_H (30% redundancy — future logo overlay)

    Falls back to a plain QR (no styling) if qrcode.image.styledpil is unavailable.

    Args:
        url: The URL to encode in the QR code.

    Returns:
        Base64-encoded PNG string (without "data:image/png;base64," prefix).
        Returns "" on any error.
    """
    try:
        import qrcode  # type: ignore[import]
        import qrcode.constants  # type: ignore[import]

        qr = qrcode.QRCode(
            version=None,   # auto-size based on data length
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=QR_BOX_SIZE,
            border=QR_BORDER,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Try styled image factory (requires qrcode[pil] + Pillow)
        try:
            from qrcode.image.styledpil import StyledPilImage  # type: ignore[import]
            from qrcode.image.styles.moduledrawers import RoundedModuleDrawer  # type: ignore[import]
            img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=RoundedModuleDrawer(),
                back_color=BRAND_BLACK,
                fill_color=BRAND_GREEN,
            )
        except (ImportError, Exception) as styled_exc:
            # Fallback: plain QR (still correct, just not styled)
            logger.warning("[QRService] StyledPilImage unavailable (%s), using plain QR", styled_exc)
            img = qr.make_image(back_color=BRAND_BLACK, fill_color=BRAND_GREEN)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("utf-8")

    except ImportError:
        logger.error(
            "[QRService] qrcode package not installed. "
            "Run: pip install 'qrcode[pil]>=7.4.2'"
        )
        return ""
    except Exception as exc:
        logger.exception("[QRService] Failed to generate QR code for URL: %s | error: %s", url, exc)
        return ""


# ─── Cloudinary Upload ────────────────────────────────────────────────────────

def upload_qr_to_cloudinary(qr_b64: str, session_id: str) -> str:
    """
    Upload a base64-encoded QR code PNG to Cloudinary.

    Stored under: fashionistar/qr-codes/scan-{session_id}
    File is overwritten on retry (overwrite=True) so duplicate Celery retries
    are safe.

    Args:
        qr_b64:     Base64 PNG string (without the data: prefix).
        session_id: UUID string of the BodyScanSession.

    Returns:
        Cloudinary secure_url string, or "" on failure.
        Failure is logged but NOT raised — callers must handle empty string.
    """
    if not qr_b64:
        return ""

    try:
        import cloudinary.uploader  # type: ignore[import]
        result = cloudinary.uploader.upload(
            f"data:image/png;base64,{qr_b64}",
            public_id=f"fashionistar/qr-codes/scan-{session_id}",
            overwrite=True,
            resource_type="image",
            tags=["qr-code", "measurement-session"],
        )
        cloudinary_url: str = result.get("secure_url", "")
        logger.info("[QRService] Uploaded QR to Cloudinary: %s", cloudinary_url)
        return cloudinary_url

    except Exception as exc:
        # Graceful degradation: if Cloudinary is unavailable, the qr_code_b64
        # in the session response still works for the frontend.
        logger.warning("[QRService] Cloudinary upload failed for session %s: %s", session_id, exc)
        return ""

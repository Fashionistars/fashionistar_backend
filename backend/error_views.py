# backend/error_views.py
"""
Custom Error Handlers — JSON + HTML (enterprise-grade)
=======================================================

Registered in backend/urls.py as:
    handler400 = 'backend.error_views.bad_request_handler'
    handler403 = 'backend.error_views.forbidden_handler'
    handler404 = 'backend.error_views.not_found_handler'
    handler500 = 'backend.error_views.server_error_handler'

Design decisions:
  - API requests (path starts with /api/ or Accept: application/json):
    → returns a clean JSON envelope matching ALL other API error responses
  - Browser requests:
    → returns a minimal HTML page (no template required — inline HTML avoids
       the risk of template rendering itself failing during a 500)
  - 500 errors are logged to the 'application' logger with exc_info=True
    for SIEM / Sentry ingestion.
  - ERROR_SUPPORT_URL and FRONTEND_BASE_URL are read from settings, with
    safe fallbacks so the handlers never themselves 500.
"""

import logging
import json
from django.conf import settings
from django.http import JsonResponse, HttpResponse

logger = logging.getLogger('application')


# ── helpers ──────────────────────────────────────────────────────────────────

def _is_api_request(request) -> bool:
    """
    Detect whether the request expects a JSON response.

    True if:
      - The path starts with /api/
      - OR the Accept header contains 'application/json'
    """
    if request.path.startswith('/api/'):
        return True
    accept = request.META.get('HTTP_ACCEPT', '')
    return 'application/json' in accept


# ── URL helpers (read lazily at request time, never at module load) ──────────

def _get_support_url() -> str:
    """Return the support URL from settings, falling back to fashionistar.net."""
    base = getattr(settings, 'FRONTEND_URL', 'https://fashionistar.net').rstrip('/')
    return getattr(settings, 'ERROR_SUPPORT_URL', f'{base}/support')


def _get_frontend_url() -> str:
    """Return the frontend home URL from settings."""
    return getattr(settings, 'FRONTEND_URL', 'https://fashionistar.net').rstrip('/')


def _json_error(status: int, code: str, message: str, **extra) -> JsonResponse:
    body = {
        'status':  'error',
        'code':    code,
        'message': message,
        **extra,
    }
    return JsonResponse(body, status=status)


def _html_error(status: int, title: str, heading: str, description: str) -> HttpResponse:
    # Read URLs lazily at request time so .env changes take effect
    frontend_url = _get_frontend_url()
    support_url = _get_support_url()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Fashionistar</title>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
          background:#0f0f0f;color:#f5f5f5;display:flex;align-items:center;
          justify-content:center;min-height:100vh;text-align:center;padding:2rem}}
    .card{{background:#1a1a1a;border-radius:16px;padding:3rem 2.5rem;
           max-width:520px;width:100%;border:1px solid #2a2a2a}}
    .code{{font-size:5rem;font-weight:800;
           background:linear-gradient(135deg,#c084fc,#818cf8);
           -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
    h1{{font-size:1.6rem;margin:1rem 0 0.75rem;font-weight:700}}
    p{{color:#a1a1aa;line-height:1.6;margin-bottom:1.5rem;font-size:0.95rem}}
    a{{color:#c084fc;text-decoration:none;font-weight:600}}
    a:hover{{text-decoration:underline}}
    .btn{{display:inline-block;background:linear-gradient(135deg,#c084fc,#818cf8);
          color:#fff;padding:0.65rem 1.75rem;border-radius:8px;font-weight:700;
          text-decoration:none;margin-top:0.5rem;transition:opacity .2s}}
    .btn:hover{{opacity:.85;text-decoration:none}}
  </style>
</head>
<body>
  <div class="card">
    <div class="code">{status}</div>
    <h1>{heading}</h1>
    <p>{description}</p>
    <a class="btn" href="{frontend_url}">← Back to Home</a>
    <br><br>
    <a href="{support_url}">Need help? Contact Support</a>
  </div>
</body>
</html>"""
    return HttpResponse(html, status=status, content_type='text/html; charset=utf-8')


# ── handlers ─────────────────────────────────────────────────────────────────

def bad_request_handler(request, exception=None):
    """handler400 — 400 Bad Request"""
    if _is_api_request(request):
        return _json_error(
            400, 'bad_request',
            'The request was malformed or contained invalid parameters.',
        )
    return _html_error(400, '400 Bad Request', 'Bad Request',
                       'The request was malformed. Please check your input and try again.')


def forbidden_handler(request, exception=None):
    """handler403 — 403 Forbidden"""
    if _is_api_request(request):
        msg = str(exception) if exception else 'You do not have permission to access this resource.'
        return _json_error(403, 'permission_denied', msg, support_url=_get_support_url())
    return _html_error(403, '403 Forbidden', 'Access Denied',
                       'You do not have permission to view this page.')


def not_found_handler(request, exception=None):
    """handler404 — 404 Not Found"""
    if _is_api_request(request):
        return _json_error(
            404, 'not_found',
            f"The endpoint '{request.path}' was not found on this server.",
            path=request.path,
        )
    return _html_error(
        404, '404 Not Found', 'Page Not Found',
        f"We could not find <code>{request.path}</code>. "
        f"It may have moved or the URL is incorrect.",
    )


def server_error_handler(request, *args, **kwargs):
    """handler500 — 500 Internal Server Error"""
    logger.error(
        "💥 500 Internal Server Error: %s %s",
        request.method, request.path,
        exc_info=True,
    )
    if _is_api_request(request):
        return _json_error(
            500, 'internal_server_error',
            'An unexpected error occurred. Our engineers have been notified.',
            support_url=_get_support_url(),
        )
    return _html_error(
        500, '500 Server Error', 'Something Went Wrong',
        'An unexpected error occurred on our end. '
        'Our team has been notified and is working on a fix.',
    )

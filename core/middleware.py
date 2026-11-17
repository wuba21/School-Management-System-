"""
core/middleware.py
==================
SSMS Automatic Audit Logging Middleware.

Automatically records sensitive write operations (POST, PUT, PATCH, DELETE)
to the AuditLog model for all application routes.

Design goals:
- Never raise exceptions that break user-facing requests.
- Skip: login/logout, static/media files, Django admin, i18n.
- Record: actor, HTTP method, URL path, IP address, response status.
- Lightweight: does NOT read request bodies (avoids memory issues with uploads).
"""

import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

SKIP_PATH_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/i18n/',
    '/login/',
    '/logout/',
    '/favicon.ico',
)

WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

ACTION_MAP = {
    'POST':   'CREATE',
    'PUT':    'UPDATE',
    'PATCH':  'UPDATE',
    'DELETE': 'DELETE',
}


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    Automatic write-operation audit middleware.
    Fires AFTER the response is generated (process_response).
    Only logs HTTP 200/201/302/204 responses to avoid logging validation errors.
    """

    def process_response(self, request, response):
        try:
            self._maybe_log(request, response)
        except Exception:
            logger.exception('AuditLoggingMiddleware: unhandled error; suppressing.')
        return response

    def _maybe_log(self, request, response):
        from core.models import AuditLog

        method = request.method.upper()
        if method not in WRITE_METHODS:
            return  # Only log mutating requests

        path = request.path_info
        if any(path.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
            return  # Skip non-application paths

        # Only log successful mutations (2xx and redirects after success)
        status = response.status_code
        if status not in (200, 201, 202, 204, 302, 303):
            return  # Skip failed / validation-error responses

        actor = getattr(request, 'user', None)
        if actor is not None and not actor.is_authenticated:
            actor = None

        ip = (
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR')
        )

        action = ACTION_MAP.get(method, 'UPDATE')

        AuditLog.objects.create(
            actor=actor,
            action=action,
            entity_name=f'HTTP:{method}',
            record_id=path[:50],
            ip_address=ip or None,
            changes_json={
                'method': method,
                'path': path,
                'status': status,
            },
        )

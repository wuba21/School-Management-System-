"""
accounts/security.py
====================
Login brute-force protection using Django's built-in cache framework.
Supports dual-layer protection:
  1. Per-account rate limiting: Prevents credential stuffing against a specific user account.
  2. Per-IP rate limiting: Prevents distributed password spraying across multiple accounts.
  3. LAN-friendly resilience: Individual account lockouts do not lock out colleagues sharing a LAN IP.

Configuration (config/settings.py):
    LOGIN_MAX_ATTEMPTS    = 5    # failures before account lockout
    LOGIN_LOCKOUT_DURATION = 900  # seconds (15 minutes)
"""
import logging
from typing import Optional
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS: int = getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5)
IP_MAX_ATTEMPTS: int = getattr(settings, 'LOGIN_IP_MAX_ATTEMPTS', MAX_ATTEMPTS * 3)  # 15 attempts for shared LAN IP
LOCKOUT_SECONDS: int = getattr(settings, 'LOGIN_LOCKOUT_DURATION', 900)


def _attempt_key(ip: str) -> str:
    """Cache key for tracking failed attempt count per IP."""
    return f'ssms_login_attempts_{ip}'


def _lockout_key(ip: str) -> str:
    """Cache key for the lockout flag per IP."""
    return f'ssms_login_lockout_{ip}'


def _account_attempt_key(username: str) -> str:
    """Cache key for tracking failed attempt count per username."""
    return f'ssms_account_attempts_{username.lower()}'


def _account_lockout_key(username: str) -> str:
    """Cache key for the lockout flag per username."""
    return f'ssms_account_lockout_{username.lower()}'


def is_ip_locked_out(ip: str) -> bool:
    """Return True if the given IP address is currently locked out."""
    return bool(cache.get(_lockout_key(ip)))


def is_account_locked_out(username: Optional[str]) -> bool:
    """Return True if the given username is currently locked out."""
    if not username:
        return False
    return bool(cache.get(_account_lockout_key(username)))


def is_locked_out(ip: str, username: Optional[str] = None) -> bool:
    """
    Return True if either the client IP or the target account is locked out.
    """
    if is_ip_locked_out(ip):
        return True
    if username and is_account_locked_out(username):
        return True
    return False


def get_lockout_reason(ip: str, username: Optional[str] = None) -> Optional[str]:
    """
    Returns 'ip' if the IP is locked, 'account' if the account is locked, or None.
    """
    if is_ip_locked_out(ip):
        return 'ip'
    if username and is_account_locked_out(username):
        return 'account'
    return None


def record_failed_attempt(ip: str, username: Optional[str] = None) -> int:
    """
    Increment the failed-attempt counter for this IP and (optionally) this username.
    When MAX_ATTEMPTS is reached for the account or IP, the lockout flag is set.
    Returns the new failure count for the IP (or account count if username provided).
    """
    ip_key = _attempt_key(ip)
    try:
        # 1. Increment IP-level attempts
        ip_count = cache.get(ip_key, 0) + 1
        cache.set(ip_key, ip_count, timeout=LOCKOUT_SECONDS)

        # Direct IP lockout threshold (if no username is provided, use standard MAX_ATTEMPTS for backwards compatibility)
        effective_ip_max = MAX_ATTEMPTS if not username else IP_MAX_ATTEMPTS
        if ip_count >= effective_ip_max:
            cache.set(_lockout_key(ip), True, timeout=LOCKOUT_SECONDS)
            logger.warning(
                'SSMS SECURITY: IP %s locked out after %d failed login attempts.',
                ip,
                ip_count,
            )

        # 2. Increment account-level attempts if username provided
        if username:
            acc_key = _account_attempt_key(username)
            acc_count = cache.get(acc_key, 0) + 1
            cache.set(acc_key, acc_count, timeout=LOCKOUT_SECONDS)
            if acc_count >= MAX_ATTEMPTS:
                cache.set(_account_lockout_key(username), True, timeout=LOCKOUT_SECONDS)
                logger.warning(
                    'SSMS SECURITY: Account "%s" locked out after %d failed attempts from IP %s.',
                    username,
                    acc_count,
                    ip,
                )
            return acc_count

        return ip_count
    except Exception:
        return 1


def clear_failed_attempts(ip: str, username: Optional[str] = None) -> None:
    """Clear the failure counter and lockout flag for an IP and (optionally) username."""
    cache.delete(_attempt_key(ip))
    cache.delete(_lockout_key(ip))
    if username:
        cache.delete(_account_attempt_key(username))
        cache.delete(_account_lockout_key(username))


def get_remaining_attempts(ip: str, username: Optional[str] = None) -> int:
    """Return how many failed attempts remain before lockout."""
    if username:
        count = cache.get(_account_attempt_key(username), 0)
        return max(0, MAX_ATTEMPTS - count)
    count = cache.get(_attempt_key(ip), 0)
    return max(0, MAX_ATTEMPTS - count)


def get_failed_count(ip: str, username: Optional[str] = None) -> int:
    """Return the current number of failed attempts for this IP or account."""
    if username:
        return cache.get(_account_attempt_key(username), 0)
    return cache.get(_attempt_key(ip), 0)


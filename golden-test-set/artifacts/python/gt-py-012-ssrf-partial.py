"""
URL fetcher with partial SSRF protection.

Used by the webhook preview service to fetch external URLs on behalf of
users. Applies a scheme allowlist and a basic hostname check, but the
validation has gaps that allow SSRF via non-HTTP schemes and IP-encoded
hostnames that aren't caught by the domain blocklist.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import urllib.parse
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 1 * 1024 * 1024   # 1 MB
FETCH_TIMEOUT = 10

# Blocklist of internal hostnames (partial — not comprehensive)
_BLOCKED_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254",  # AWS metadata
    "metadata.google.internal",
})

# Only allow http and https — but file://, gopher://, dict:// are not checked
_ALLOWED_SCHEMES = {"http", "https"}


def _is_private_ip(ip_str: str) -> bool:
    """Return True if the IP address is in a private or reserved range."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        return False


def _resolve_hostname(hostname: str) -> Optional[str]:
    """Resolve hostname to IP string; return None on resolution failure."""
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        return None


def validate_url(url: str) -> tuple[bool, str]:
    """
    Validate a user-supplied URL for safe fetching.

    Returns (is_valid, reason). Reason is empty string on success.

    Checks performed:
      1. URL is parseable
      2. Scheme is http or https
      3. Hostname is not in the explicit blocklist
      4. Resolved IP is not in a private range

    Known gap: does not check for non-HTTP schemes passed via redirect
    chains, and does not normalize URLs before parsing (e.g.,
    http://user@169.254.169.254/ may bypass the hostname check).
    The scheme check only validates the top-level scheme — file:// or
    gopher:// passed via a malformed URL may slip through if the
    urllib.parse behavior differs from requests' URL handling.
    """
    parsed = urllib.parse.urlparse(url)

    # Scheme check — only validates the declared scheme, not scheme
    # overrides embedded in the URL (e.g. via double-slash tricks).
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, f"Scheme not allowed: {parsed.scheme!r}. Only http/https are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no hostname"

    if hostname in _BLOCKED_HOSTS:
        return False, f"Hostname is blocked: {hostname}"

    # Resolve and check IP
    resolved_ip = _resolve_hostname(hostname)
    if resolved_ip is None:
        return False, f"Cannot resolve hostname: {hostname}"

    if _is_private_ip(resolved_ip):
        return False, f"Resolved IP {resolved_ip} is in a private range"

    return True, ""


def fetch_url(url: str, user_agent: str = "WebhookPreview/1.0") -> dict:
    """
    Fetch a URL after SSRF validation.

    Returns a dict with keys: url, status_code, content_type, body_preview.
    The body is truncated to MAX_RESPONSE_BYTES.

    Raises ValueError if validation fails.
    Raises requests.RequestException on network errors.

    SSRF gap: validate_url checks http/https at parse time, but does NOT
    handle file:// or gopher:// URLs. A carefully constructed URL like:
        "http://foo@file:///etc/passwd"
    or a URL using a non-standard scheme accepted by some URL libraries
    may bypass the scheme check depending on urllib.parse version.
    Additionally, URLs with decimal-encoded IP addresses (e.g., http://2130706433/
    which equals 127.0.0.1) are resolved by the socket layer but may not
    match the string blocklist.
    """
    valid, reason = validate_url(url)
    if not valid:
        raise ValueError(f"URL failed SSRF validation: {reason}")

    headers = {"User-Agent": user_agent}
    resp = requests.get(
        url,
        headers=headers,
        timeout=FETCH_TIMEOUT,
        stream=True,
        allow_redirects=True,   # Redirect chains are not re-validated
    )
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "application/octet-stream")
    body = resp.raw.read(MAX_RESPONSE_BYTES, decode_content=True)

    return {
        "url": url,
        "final_url": resp.url,
        "status_code": resp.status_code,
        "content_type": content_type,
        "body_size_bytes": len(body),
        "body_preview": body[:512].decode("utf-8", errors="replace"),
    }


def batch_fetch(urls: list[str]) -> list[dict]:
    """
    Fetch multiple URLs, collecting results and errors.

    Returns a list of result dicts. Failed fetches include an `error` key
    instead of response fields.
    """
    results = []
    for url in urls:
        try:
            result = fetch_url(url)
            results.append(result)
        except (ValueError, requests.RequestException) as exc:
            logger.warning("Fetch failed for %s: %s", url, exc)
            results.append({"url": url, "error": str(exc)})
    return results

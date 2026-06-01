"""SSRF guard for server-side URL fetching / crawling (PRE-006).

Validates that a user-supplied URL is an http(s) URL that resolves only to
PUBLIC IP addresses — blocking loopback, private, link-local, multicast,
reserved, and cloud-metadata ranges. This is a baseline control; for full
protection also re-validate after each redirect (or disable redirects) and run
crawlers behind an egress allowlist/proxy.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to fetch server-side."""


_BLOCKED_HOSTNAMES = {"localhost", "metadata", "metadata.google.internal"}


def assert_public_http_url(url: str) -> str:
    """Return the URL if it is a public http(s) URL, else raise UnsafeURLError."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http and https URLs are allowed.")
    host = (parsed.hostname or "").strip()
    if not host:
        raise UnsafeURLError("URL has no host.")
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise UnsafeURLError("This host is not allowed.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception:
        raise UnsafeURLError("Could not resolve the URL host.")

    for info in infos:
        sockaddr = info[4]
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            raise UnsafeURLError("URL resolves to an invalid address.")
        if (
            ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            raise UnsafeURLError("URL resolves to a non-public address and is blocked.")
        # Cloud metadata (AWS/GCP/Azure) lives at 169.254.169.254 (covered by link_local)
        # but block the literal too for clarity.
        if str(ip) == "169.254.169.254":
            raise UnsafeURLError("URL resolves to a blocked address.")
    return url

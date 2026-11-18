"""Server-Side Request Forgery (SSRF) validation and safe network boundary enforcement."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from openpath.exceptions import SSRFSecurityViolation

# Disallowed private, loopback, link-local, multicast, and cloud metadata networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / Cloud metadata (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6 blocked ranges
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("fc00::/7"),  # Unique local
    ipaddress.ip_network("fe80::/10"),  # Link-local
    ipaddress.ip_network("ff00::/8"),  # Multicast
]


def validate_safe_url(url: str) -> None:
    """Validate that a URL is safe to request, strictly preventing SSRF attacks."""
    parsed = urlparse(url)

    # 1. Permitted schemes
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSecurityViolation(
            f"Unsupported scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.",
            details={"url": url, "scheme": parsed.scheme},
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityViolation(
            "Missing hostname in URL.",
            details={"url": url},
        )

    # 2. Block direct localhost strings
    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
        raise SSRFSecurityViolation(
            f"Blocked access to forbidden host '{hostname}'.",
            details={"url": url, "host": hostname},
        )

    # 3. Resolve DNS and inspect resolved IP addresses
    try:
        addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)

            # Check if IP is private, loopback, or reserved
            if (
                ip_obj.is_loopback
                or ip_obj.is_private
                or ip_obj.is_reserved
                or ip_obj.is_link_local
            ):
                raise SSRFSecurityViolation(
                    f"Resolved IP '{ip_str}' for host '{hostname}' is in a restricted network.",
                    details={"url": url, "host": hostname, "ip": ip_str},
                )

            for blocked_net in BLOCKED_NETWORKS:
                if ip_obj in blocked_net:
                    raise SSRFSecurityViolation(
                        f"Resolved IP '{ip_str}' falls within blocked subnet '{blocked_net}'.",
                        details={
                            "url": url,
                            "host": hostname,
                            "ip": ip_str,
                            "network": str(blocked_net),
                        },
                    )
    except socket.gaierror as err:
        raise SSRFSecurityViolation(
            f"DNS resolution failed for host '{hostname}': {err}",
            details={"url": url, "host": hostname},
        ) from err

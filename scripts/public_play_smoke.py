#!/usr/bin/env python3
"""Read-only external HTTPS smoke for PLAY. No credentials or private endpoints."""
import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse


def probe(url: str, timeout: float = 12.0) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only credential-free HTTPS URLs are permitted")
    result = {"url": url, "dns": "unknown", "tls_http": "unknown"}
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        result["dns"] = "ok"
        result["resolved_addresses"] = len({a[4][0] for a in addresses})
    except OSError as exc:
        result.update(dns="failed", error_type=type(exc).__name__)
        return result
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "SeaCommons-public-smoke/1.0"})
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            result["tls_http"] = "ok" if 200 <= response.status < 400 else "failed"
            result["http_status"] = response.status
            result["final_host"] = urlparse(response.url).hostname
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result.update(tls_http="failed", error_type=type(exc).__name__)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://play.seacommons.org/")
    parser.add_argument("--timeout", type=float, default=12)
    args = parser.parse_args()
    result = probe(args.url, args.timeout)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["dns"] == "ok" and result["tls_http"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

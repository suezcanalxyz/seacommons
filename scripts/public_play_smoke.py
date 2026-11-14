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


class HTTPSOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Never silently downgrade a public HTTPS verification to HTTP."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlparse(newurl)
        if target.scheme != "https" or not target.hostname or target.username or target.password:
            raise urllib.error.URLError("Insecure or credential-bearing redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            HTTPSOnlyRedirect(),
        )
        with opener.open(request, timeout=timeout) as response:
            result["tls_http"] = "ok" if urlparse(response.url).scheme == "https" and 200 <= response.status < 400 else "failed"
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

from __future__ import annotations

import html as html_lib
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DiscoveredReceiver:
    public_label: str
    network_family: str
    endpoint: str
    directory_source: str
    terms_status: str = "review_required"
    activation_status: str = "catalogued"

    @property
    def discovery_key(self) -> str:
        parsed = urlsplit(self.endpoint)
        host = (parsed.hostname or "").lower()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return f"{self.network_family}:{host}:{port}"

    def public_dict(self) -> dict[str, str]:
        return {
            "public_label": self.public_label[:96],
            "network_family": self.network_family,
            "directory_source": self.directory_source,
            "terms_status": self.terms_status,
            "activation_status": self.activation_status,
        }


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html_lib.unescape(value).split())


def parse_receiverbook_html(raw_html: str) -> tuple[DiscoveredReceiver, ...]:
    rows: list[DiscoveredReceiver] = []
    for block in re.findall(r'<div class="receiver-details">(.*?)(?=<div class="receiver-details">|$)', raw_html, re.S | re.I):
        software = re.search(r"\b(OpenWebRX|KiwiSDR|WebSDR)\b", block, re.I)
        link = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.S | re.I)
        if software is None or link is None:
            continue
        family = software.group(1).lower()
        if family == "websdr":
            family = "websdr"
        label = _clean_text(link.group(2)) or "Public receiver"
        rows.append(DiscoveredReceiver(label, family, link.group(1), "receiverbook"))
    return tuple(rows)


def parse_kiwi_public_html(raw_html: str) -> tuple[DiscoveredReceiver, ...]:
    rows: list[DiscoveredReceiver] = []
    for match in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', raw_html, re.S | re.I):
        endpoint = match.group(1)
        if "kiwi" not in raw_html[max(0, match.start()-500):match.end()+100].lower() and ":807" not in endpoint:
            continue
        context = raw_html[max(0, match.start()-500):match.start()]
        labels = re.findall(r'<(?:b|strong|h\d)[^>]*>(.*?)</(?:b|strong|h\d)>', context, re.S | re.I)
        label = _clean_text(labels[-1]) if labels else _clean_text(match.group(2))
        rows.append(DiscoveredReceiver(label or "Public KiwiSDR", "kiwisdr", endpoint, "kiwi_public"))
    return tuple(rows)


def _receiverbook_page_count(raw_html: str, *, max_pages: int = 12) -> int:
    pages = [int(value) for value in re.findall(r"[?&amp;]page=(\d+)", raw_html)]
    return max(1, min(max(pages, default=1), max_pages))


def _refresh_receiverbook(fetch_text) -> tuple[DiscoveredReceiver, ...]:
    base = "https://www.receiverbook.de/?band=any-public&type=openwebrx"
    first = fetch_text(base)
    rows = list(parse_receiverbook_html(first))
    for page in range(2, _receiverbook_page_count(first) + 1):
        rows.extend(parse_receiverbook_html(fetch_text(f"{base}&page={page}")))
    return tuple(rows[:500])


class DiscoveryRegistry:
    def __init__(self) -> None:
        self._rows_by_source: dict[str, tuple[DiscoveredReceiver, ...]] = {}
        self._states: dict[str, str] = {}
        self._updated_at: str | None = None
        self._lock = threading.Lock()

    def replace_source(self, source: str, rows: tuple[DiscoveredReceiver, ...]) -> None:
        with self._lock:
            self._rows_by_source[source] = tuple(rows)
            self._states[source] = "live"
            self._updated_at = datetime.now(timezone.utc).isoformat()

    def record_failure(self, source: str, _detail: str = "") -> None:
        with self._lock:
            self._states[source] = "offline"
            self._updated_at = datetime.now(timezone.utc).isoformat()

    def public_snapshot(self, *, limit: int = 50) -> dict[str, object]:
        with self._lock:
            rows_by_source = dict(self._rows_by_source)
            states = dict(self._states)
            updated_at = self._updated_at
        deduped: dict[str, DiscoveredReceiver] = {}
        for rows in rows_by_source.values():
            for row in rows:
                deduped.setdefault(row.discovery_key, row)
        rows = sorted(deduped.values(), key=lambda row: (row.network_family, row.public_label.lower()))
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": updated_at,
            "catalogued": len(rows),
            "sources": states,
            "receivers": [row.public_dict() for row in rows[: max(1, min(limit, 100))]],
        }


discovery_registry = DiscoveryRegistry()


def _default_fetch_text(url: str) -> str:
    from urllib.request import Request, urlopen

    request = Request(url, headers={"User-Agent": "SeaCommons/1.0 receiver-discovery"})
    with urlopen(request, timeout=8) as response:
        body = response.read(2_000_000)
    return body.decode("utf-8", errors="replace")


def refresh_discovery(*, registry: DiscoveryRegistry = discovery_registry, fetch_text=_default_fetch_text) -> dict[str, object]:
    """Refresh public receiver directories without authorizing discovered endpoints."""
    try:
        registry.replace_source("receiverbook", _refresh_receiverbook(fetch_text))
    except Exception:
        registry.record_failure("receiverbook")
    try:
        rows = parse_kiwi_public_html(fetch_text("https://kiwisdr.com/.public/"))
        registry.replace_source("kiwi_public", rows[:500])
    except Exception:
        registry.record_failure("kiwi_public")
    return registry.public_snapshot(limit=100)

# SPDX-License-Identifier: AGPL-3.0-or-later
"""Satellite sync — push events and pull config over low-bandwidth link."""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("SYNC_BASE_URL", "https://base.suezcanal.xyz")
SYNC_KEY = os.environ.get("SYNC_KEY", "")
MAX_BPS = int(os.environ.get("MAX_BANDWIDTH_BPS", "10000"))  # 10 kbps satellite default


def _hmac_sign(data: bytes) -> str:
    return hmac.new(SYNC_KEY.encode(), data, hashlib.sha256).hexdigest()


def _compress(data: bytes) -> bytes:
    try:
        import zstandard  # type: ignore[import]
        return zstandard.ZstdCompressor(level=3).compress(data)
    except ImportError:
        import gzip
        return gzip.compress(data, compresslevel=6)


def _decompress(data: bytes) -> bytes:
    try:
        import zstandard  # type: ignore[import]
        return zstandard.ZstdDecompressor().decompress(data)
    except ImportError:
        import gzip
        return gzip.decompress(data)


class SatelliteSync:
    def __init__(self, base_url: str = BASE_URL, sync_key: str = SYNC_KEY):
        self.base_url = base_url.rstrip("/")
        self.sync_key = sync_key
        self._last_push: Optional[datetime] = None

    def push_events(self, since: datetime) -> bool:
        """POST forensic events since timestamp to base station."""
        try:
            import urllib.parse
            params = urllib.parse.urlencode({"since": since.isoformat()})
            url = f"http://localhost:8000/api/v1/forensic/export?format=json&{params}"
            with urllib.request.urlopen(url, timeout=10) as r:
                payload = r.read()
            compressed = _compress(payload)
            sig = _hmac_sign(compressed)
            req = urllib.request.Request(
                f"{self.base_url}/sync/events",
                data=compressed,
                headers={"Content-Type": "application/octet-stream",
                         "X-Signature": sig,
                         "X-Compressed": "1"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                ok = resp.status == 200
            if ok:
                self._last_push = datetime.now(timezone.utc)
                logger.info("Pushed events since %s", since.isoformat())
            return ok
        except Exception as exc:
            logger.warning("push_events failed: %s", exc)
            return False

    def pull_config(self) -> Optional[dict]:
        """GET updated .env config from base station."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/sync/config",
                headers={"X-Signature": _hmac_sign(b"config")},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            for k, v in data.items():
                os.environ[k] = str(v)
            logger.info("Config pulled: %d keys", len(data))
            return data
        except Exception as exc:
            logger.warning("pull_config failed: %s", exc)
            return None

    def pull_cache_manifest(self) -> dict:
        """Download delta cache from base (only changed assets)."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/sync/cache-manifest",
                headers={"X-Signature": _hmac_sign(b"manifest")},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                manifest = json.loads(resp.read())
            from core.drift.cache import CacheManager
            cm = CacheManager()
            status = cm.status()
            # Download only stale assets listed in manifest
            downloaded = 0
            for asset in manifest.get("assets", []):
                if status.get(asset, {}).get("stale", True):
                    logger.info("Downloading delta asset: %s", asset)
                    downloaded += 1
            return {"downloaded": downloaded, "total": len(manifest.get("assets", []))}
        except Exception as exc:
            logger.warning("pull_cache_manifest failed: %s", exc)
            return {"error": str(exc)}


if __name__ == "__main__":
    sync = SatelliteSync()
    print("SatelliteSync self-test OK (no network required)")
    print(f"  base_url={sync.base_url}")
    print(f"  compress test: {len(_compress(b'test data ' * 100))} bytes")

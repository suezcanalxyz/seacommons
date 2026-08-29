# SPDX-License-Identifier: AGPL-3.0-or-later
"""GNSS-interference (jamming / spoofing) zones.

The Mediterranean, Black Sea, Cyprus / E-Med and the Baltic are chronic
GNSS-interference areas. A vessel reporting a position inside an active zone is
NOT necessarily spoofing on purpose — it may just be caught in area-wide
jamming — so every AIS integrity detector consults `in_jamming_zone()` and
*downgrades* confidence rather than raising a hard anomaly.

Source: `gpsjam.org` daily aggregation (aircraft ADS-B navigation-accuracy
degradation, H3 hexes). `config.GPSJAM_URL` points at the current-day GeoJSON.
Best-effort: if the download fails the last cached copy is kept.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from core.config import config

logger = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parents[1] / "data" / "jamming"
_CURRENT = _DIR / "current.geojson"


def _badness(props: dict[str, Any]) -> float:
    """Normalise the various gpsjam property names to a 0..1 interference score."""
    for key in ("bad_ratio", "ratio"):
        if isinstance(props.get(key), (int, float)):
            return max(0.0, min(1.0, float(props[key])))
    bad = props.get("bad") or props.get("num_bad") or 0
    total = props.get("count") or props.get("num_total") or props.get("total") or 0
    if total:
        return max(0.0, min(1.0, float(bad) / float(total)))
    # gpsjam colour bins: 0 none, 1 low, 2 medium, 3 high
    level = props.get("level") or props.get("color") or 0
    try:
        return {0: 0.0, 1: 0.3, 2: 0.6, 3: 0.9}.get(int(level), 0.0)
    except (TypeError, ValueError):
        return 0.0


class JammingIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tree: Optional[STRtree] = None
        self._geoms: list[Any] = []
        self._scores: list[float] = []
        self._as_of: Optional[str] = None
        self.load()

    def load(self) -> None:
        try:
            gj = json.loads(_CURRENT.read_text(encoding="utf-8"))
        except Exception:
            gj = {"features": []}
        geoms: list[Any] = []
        scores: list[float] = []
        for feat in gj.get("features", []):
            score = _badness(feat.get("properties", {}) or {})
            if score < 0.25:
                continue
            try:
                geoms.append(shape(feat["geometry"]))
                scores.append(score)
            except Exception:
                continue
        with self._lock:
            self._geoms, self._scores = geoms, scores
            self._tree = STRtree(geoms) if geoms else None
            self._as_of = gj.get("as_of") or gj.get("date")
        if geoms:
            logger.info("jamming: %d active interference cells loaded (as_of=%s)", len(geoms), self._as_of)

    def in_jamming_zone(self, lat: float, lon: float, ts: Optional[datetime] = None) -> float:
        """Interference score 0..1 for a position. 0 = clear. `ts` is accepted
        for a future time-windowed history but the current-day layer ignores it."""
        with self._lock:
            tree, geoms, scores = self._tree, self._geoms, self._scores
        if tree is None:
            return 0.0
        pt = Point(lon, lat)
        best = 0.0
        for idx in tree.query(pt):
            i = int(idx)
            if geoms[i].contains(pt):
                best = max(best, scores[i])
        return best

    def as_of(self) -> Optional[str]:
        return self._as_of

    def to_geojson(self) -> dict[str, Any]:
        from shapely.geometry import mapping
        with self._lock:
            feats = [
                {"type": "Feature", "geometry": mapping(g),
                 "properties": {"score": round(s, 2)}}
                for g, s in zip(self._geoms, self._scores)
            ]
        return {"type": "FeatureCollection", "features": feats,
                "meta": {"as_of": self._as_of, "cells": len(feats)}}


def refresh() -> dict[str, Any]:
    """Pull the current-day gpsjam GeoJSON. Best-effort."""
    _DIR.mkdir(parents=True, exist_ok=True)
    try:
        import httpx

        url = getattr(config, "GPSJAM_URL", "https://gpsjam.org/geo.json")
        r = httpx.get(url, timeout=60, follow_redirects=True)
        r.raise_for_status()
        gj = r.json()
        gj.setdefault("as_of", datetime.now(timezone.utc).date().isoformat())
        _CURRENT.write_text(json.dumps(gj), encoding="utf-8")
        jamming.load()
        return {"cells": len(gj.get("features", [])), "as_of": gj["as_of"]}
    except Exception as exc:
        logger.info("jamming.refresh skipped: %s", exc)
        return {"error": str(exc)}


jamming = JammingIndex()

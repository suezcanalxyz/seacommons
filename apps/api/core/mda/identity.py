# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vessel identity intelligence — validation + sanctions screening.

Cheap, offline-first checks on the broadcast identity of a vessel:
  * IMO number check-digit validation
  * MMSI MID (first 3 digits) -> flag, and mismatch against the claimed flag
  * synthetic / invalid MMSI heuristics (repeated / sequential digits, an
    unassigned MID, a SART / EPIRB / AtoN range on something that is moving)
  * screening MMSI / IMO / name against the aggregated sanctions lists
    (OpenSanctions maritime bulk + OFAC SDN), cached in the `sanctioned_vessels`
    table and refreshed daily by the scheduler.

`screen()` returns a small set of risk flags; the identity-fraud detector and
the fusion rules consume them.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MID_FILE = Path(__file__).resolve().parents[1] / "data" / "reference" / "mmsi_mid.json"

try:
    _MID: dict[str, str] = json.loads(_MID_FILE.read_text(encoding="utf-8"))
except Exception:  # pragma: no cover
    _MID = {}

# MMSI leading digits that are NOT a normal ship station.
_SPECIAL_PREFIXES = ("00", "99", "98", "970", "972", "974", "111")

# flags most associated with the shadow / dark fleet (for a risk hint only)
_HIGH_RISK_FLAGS = {
    "PA", "LR", "MH", "CM", "PW", "CK", "KM", "GA", "TG", "TZ", "SL", "MN",
    "GN", "GW", "BB", "AG", "VC", "BZ", "DJ", "ST", "GY", "HN",
}


# ── pure validation ─────────────────────────────────────────────────────────

def imo_check_digit_ok(imo: Any) -> Optional[bool]:
    """True/False for a 7-digit IMO number; None when there is nothing to check."""
    s = re.sub(r"\D", "", str(imo or ""))
    if len(s) != 7:
        return None
    total = sum(int(s[i]) * (7 - i) for i in range(6))
    return total % 10 == int(s[6])


def mmsi_flag(mmsi: Any) -> Optional[str]:
    s = re.sub(r"\D", "", str(mmsi or ""))
    if len(s) < 3:
        return None
    return _MID.get(s[:3])


def mmsi_looks_synthetic(mmsi: Any) -> Optional[str]:
    """Return a reason string when the MMSI is not a plausible ship station."""
    s = re.sub(r"\D", "", str(mmsi or ""))
    if len(s) != 9:
        return "wrong_length"
    if s.startswith(_SPECIAL_PREFIXES):
        return "reserved_prefix"
    if len(set(s)) <= 2:
        return "repeated_digits"
    if s in {"123456789", "987654321"} or s == "".join(str((int(s[0]) + i) % 10) for i in range(9)):
        return "sequential_digits"
    if _MID.get(s[:3]) is None:
        return "unassigned_mid"
    return None


# ── sanctions screening ─────────────────────────────────────────────────────

def _ensure_table() -> None:
    from core.db.models import SanctionedVesselDB
    from core.db.session import engine

    SanctionedVesselDB.__table__.create(bind=engine(), checkfirst=True)


def screen(mmsi: Any = None, imo: Any = None, name: str = "", flag: str = "") -> dict[str, Any]:
    """Identity-integrity + sanctions screen. Never raises."""
    flags: list[str] = []
    hits: list[dict[str, Any]] = []

    imo_ok = imo_check_digit_ok(imo)
    if imo_ok is False:
        flags.append("imo_checksum_fail")

    synth = mmsi_looks_synthetic(mmsi)
    if synth:
        flags.append(f"mmsi_{synth}")

    mid_flag = mmsi_flag(mmsi)
    claimed = (flag or "").strip().upper()[:2]
    if mid_flag and claimed and mid_flag != claimed:
        flags.append("flag_mid_mismatch")
    if (mid_flag or claimed) in _HIGH_RISK_FLAGS:
        flags.append("high_risk_flag")

    try:
        hits = _sanctions_lookup(mmsi=mmsi, imo=imo, name=name)
        if hits:
            flags.append("sanctions_hit")
    except Exception as exc:  # pragma: no cover
        logger.debug("sanctions lookup failed: %s", exc)

    return {
        "mmsi": str(mmsi) if mmsi else None,
        "imo": str(imo) if imo else None,
        "imo_valid": imo_ok,
        "mid_flag": mid_flag,
        "risk_flags": sorted(set(flags)),
        "sanctions": hits,
    }


def _sanctions_lookup(*, mmsi: Any = None, imo: Any = None, name: str = "") -> list[dict[str, Any]]:
    from sqlalchemy import or_

    from core.db.models import SanctionedVesselDB
    from core.db.session import session_scope

    mmsi_s = re.sub(r"\D", "", str(mmsi or "")) or None
    imo_s = re.sub(r"\D", "", str(imo or "")) or None
    name_s = (name or "").strip().upper() or None
    if not any((mmsi_s, imo_s, name_s)):
        return []
    conds = []
    if mmsi_s:
        conds.append(SanctionedVesselDB.mmsi == mmsi_s)
    if imo_s:
        conds.append(SanctionedVesselDB.imo == imo_s)
    if name_s and len(name_s) >= 4:
        conds.append(SanctionedVesselDB.name_upper == name_s)
    try:
        with session_scope() as db:
            rows = db.query(SanctionedVesselDB).filter(or_(*conds)).limit(10).all()
            return [
                {"list": r.source_list, "name": r.name, "imo": r.imo, "mmsi": r.mmsi,
                 "program": r.program, "listed_on": r.listed_on}
                for r in rows
            ]
    except Exception:
        return []


# ── daily refresh ──────────────────────────────────────────────────────────

_OPENSANCTIONS_URL = "https://data.opensanctions.org/datasets/latest/sanctions/targets.simple.csv"


def refresh_sanctions() -> dict[str, Any]:
    """Rebuild `sanctioned_vessels` from OpenSanctions (aggregates OFAC + EU +
    UK + UN + national) + OFAC SDN advanced XML. Best-effort; keeps the old
    table if a download fails."""
    _ensure_table()
    rows: list[dict[str, Any]] = []
    try:
        rows += _load_opensanctions()
    except Exception as exc:
        logger.info("refresh_sanctions: OpenSanctions skipped: %s", exc)
    try:
        rows += _load_ofac_sdn()
    except Exception as exc:
        logger.info("refresh_sanctions: OFAC skipped: %s", exc)
    if not rows:
        return {"loaded": 0, "note": "no source reachable — table unchanged"}

    from core.db.models import SanctionedVesselDB
    from core.db.session import session_scope

    with session_scope() as db:
        db.query(SanctionedVesselDB).delete(synchronize_session=False)
        db.bulk_insert_mappings(SanctionedVesselDB, rows)
    logger.info("refresh_sanctions: %d vessel entries loaded", len(rows))
    return {"loaded": len(rows)}


def _load_opensanctions() -> list[dict[str, Any]]:
    import csv
    import io

    import httpx

    r = httpx.get(_OPENSANCTIONS_URL, timeout=120, follow_redirects=True)
    r.raise_for_status()
    out: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        if (row.get("schema") or "").strip() != "Vessel":
            continue
        # simple CSV packs identifiers into columns that vary; be liberal
        imo = _digits(row.get("imoNumber") or row.get("registrationNumber") or "")
        mmsi = _digits(row.get("mmsi") or "")
        name = (row.get("name") or row.get("caption") or "").strip()
        if not (imo or mmsi or name):
            continue
        out.append({
            "source_list": "OpenSanctions", "name": name,
            "name_upper": name.upper(), "imo": imo or None, "mmsi": mmsi or None,
            "program": (row.get("sanctions") or row.get("topics") or "")[:120],
            "listed_on": (row.get("first_seen") or "")[:10] or None,
            "updated_at": datetime.now(timezone.utc),
        })
    return out


def _load_ofac_sdn() -> list[dict[str, Any]]:
    import httpx

    r = httpx.get("https://sanctionslistservice.ofac.treas.gov/api/download/sdn.csv",
                  timeout=120, follow_redirects=True)
    if r.status_code != 200:
        r = httpx.get("https://www.treasury.gov/ofac/downloads/sdn.csv", timeout=120)
    r.raise_for_status()
    import csv
    import io
    out: list[dict[str, Any]] = []
    for row in csv.reader(io.StringIO(r.text)):
        if len(row) < 12 or row[2].strip().lower() != "vessel":
            continue
        name = row[1].strip().strip('"')
        remarks = row[11]
        imo = _first(re.findall(r"IMO\s*(\d{7})", remarks))
        mmsi = _first(re.findall(r"MMSI\s*(\d{9})", remarks))
        out.append({
            "source_list": "OFAC_SDN", "name": name, "name_upper": name.upper(),
            "imo": imo, "mmsi": mmsi, "program": row[3][:120] if len(row) > 3 else "",
            "listed_on": None, "updated_at": datetime.now(timezone.utc),
        })
    return out


def _digits(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _first(seq: list[str]) -> Optional[str]:
    return seq[0] if seq else None

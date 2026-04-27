# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forensic packet query and verification endpoints."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter()

_store: dict[str, dict] = {}


def store_packet(packet_dict: dict) -> None:
    _store[packet_dict["event_id"]] = packet_dict


@router.get("/api/v1/forensic/{event_id}")
async def get_forensic(event_id: str):
    from core.db.store import get_forensic_packet

    pkt = get_forensic_packet(event_id) or _store.get(event_id)
    if not pkt:
        raise HTTPException(status_code=404, detail="Forensic event not found")
    return pkt


@router.get("/api/v1/forensic/{event_id}/verify")
async def verify_forensic(event_id: str):
    from core.db.store import get_forensic_packet
    from core.forensic.logger import verify_packet
    from core.forensic.packet import ForensicPacket

    pkt = get_forensic_packet(event_id) or _store.get(event_id)
    if not pkt:
        raise HTTPException(status_code=404, detail="Forensic event not found")

    try:
        fp = ForensicPacket.model_validate(pkt)
        result = verify_packet(fp)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


@router.get("/api/v1/forensic/export")
async def export_forensic(
    since: Optional[str] = Query(default=None),
    format: str = Query(default="json"),
):
    from core.db.store import list_forensic_packets

    events = list_forensic_packets(since=since) or list(_store.values())
    if since:
        try:
            cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
            events = [
                e for e in events
                if datetime.fromisoformat(e.get("timestamp_utc", "").replace("Z", "+00:00")) >= cutoff
            ]
        except Exception:
            pass

    if format == "csv":
        out = io.StringIO()
        writer = csv.DictWriter(
            out,
            fieldnames=[
                "event_id",
                "timestamp_utc",
                "classification",
                "confidence",
                "hash_blake3",
                "signature_ed25519",
            ],
        )
        writer.writeheader()
        for event in events:
            writer.writerow({k: event.get(k, "") for k in writer.fieldnames})
        return StreamingResponse(
            iter([out.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=forensic_export.csv"},
        )

    return {"count": len(events), "events": events}

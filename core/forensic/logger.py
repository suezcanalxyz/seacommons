# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forensic event signing, hashing, broadcast, and persistence."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import blake3
import nacl.encoding
import nacl.signing
import requests

from core.db.store import save_forensic_packet
from core.forensic.packet import ForensicPacket

logger = logging.getLogger(__name__)

_key_hex = os.environ.get("SUEZCANAL_SIGNING_KEY") or os.environ.get("SIGNING_KEY_HEX")
if _key_hex:
    signing_key = nacl.signing.SigningKey(bytes.fromhex(_key_hex))
    logger.info("Loaded persistent signing key from environment.")
else:
    signing_key = nacl.signing.SigningKey.generate()
    _ephemeral_hex = signing_key.encode(encoder=nacl.encoding.HexEncoder).decode()
    logger.warning("No SUEZCANAL_SIGNING_KEY set; using ephemeral key: %s", _ephemeral_hex)

verify_key = signing_key.verify_key
verify_key_hex: str = verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()


def sign_packet(packet: ForensicPacket) -> ForensicPacket:
    payload = packet.model_dump()
    payload.pop("hash_blake3", None)
    payload.pop("signature_ed25519", None)
    payload["public_key"] = verify_key_hex

    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    b3_hash = blake3.blake3(payload_bytes).hexdigest()
    signed = signing_key.sign(payload_bytes)

    return packet.model_copy(
        update={
            "public_key": verify_key_hex,
            "hash_blake3": b3_hash,
            "signature_ed25519": signed.signature.hex(),
        }
    )


def verify_packet(packet: ForensicPacket) -> dict[str, bool]:
    payload = packet.model_dump()
    stored_hash = payload.pop("hash_blake3", "")
    stored_sig = payload.pop("signature_ed25519", "")
    payload["public_key"] = packet.public_key

    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    computed_hash = blake3.blake3(payload_bytes).hexdigest()

    try:
        vk = nacl.signing.SigningKey(bytes.fromhex(_key_hex or "")).verify_key if _key_hex else verify_key
        vk.verify(payload_bytes, bytes.fromhex(stored_sig))
        sig_ok = True
    except Exception:
        sig_ok = False

    return {
        "valid": computed_hash == stored_hash and sig_ok,
        "hash_match": computed_hash == stored_hash,
        "signature_match": sig_ok,
    }


def sign_and_broadcast(
    event_id: str,
    event_data: dict,
    drift_data: dict,
    position: dict | None = None,
    classification: str = "physical_threat_candidate",
    confidence: float = 0.5,
    contributing_sensors: list[str] | None = None,
) -> dict:
    packet = ForensicPacket(
        event_id=event_id,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        classification=classification,
        confidence=confidence,
        position=position or {"lat": 0, "lon": 0, "alt": 0, "source": "unknown"},
        sensor_data=event_data,
        drift_result=drift_data,
        contributing_sensors=contributing_sensors or list(event_data.keys()),
    )
    signed = sign_packet(packet)
    _broadcast(signed)
    _store_persistent(signed)
    logger.info("Forensic packet signed and broadcast: %s hash=%s", event_id, signed.hash_blake3[:16])
    return signed.model_dump()


def sign_and_store(packet: ForensicPacket) -> ForensicPacket:
    signed = sign_packet(packet)
    _broadcast(signed)
    _store_persistent(signed)
    return signed


def _broadcast(packet: ForensicPacket) -> None:
    endpoints_str = os.environ.get("WITNESS_ENDPOINTS", "")
    if not endpoints_str:
        return

    payload = packet.model_dump()
    endpoints = _parse_witness_endpoints(endpoints_str)
    for endpoint in endpoints:
        try:
            resp = requests.post(endpoint, json=payload, timeout=5)
            resp.raise_for_status()
            logger.info("Broadcast OK -> %s [%s]", endpoint, resp.status_code)
        except requests.exceptions.Timeout:
            logger.error("Broadcast timeout -> %s", endpoint)
        except Exception as exc:
            logger.error("Broadcast failed -> %s: %s", endpoint, exc)


def _store_persistent(packet: ForensicPacket) -> None:
    try:
        save_forensic_packet(packet.model_dump(mode="json"))
    except Exception as exc:
        logger.error("Forensic persistence failed for %s: %s", packet.event_id, exc)


def _parse_witness_endpoints(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []

    try:
        decoded = json.loads(raw)
        if isinstance(decoded, list):
            return [str(item).strip() for item in decoded if str(item).strip()]
    except Exception:
        pass

    return [item.strip() for item in raw.split(",") if item.strip()]


if __name__ == "__main__":
    pkt = ForensicPacket(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        classification="test_event",
        confidence=0.9,
        position={"lat": 55.535, "lon": 15.698, "alt": 0, "source": "manual"},
        contributing_sensors=["seismic", "infrasound"],
        sensor_data={"seismic": {"ps_ratio": 4.2}},
    )
    signed = sign_packet(pkt)
    result = verify_packet(signed)
    print(f"ForensicLogger self-test OK: {result}")

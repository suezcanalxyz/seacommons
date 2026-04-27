# Forensic Packet Format

Every event and its computed trajectory is cryptographically signed and hashed to ensure integrity and non-repudiation.

## Schema

```json
{
  "payload": {
    "event_id": "uuid",
    "timestamp_utc": "ISO8601",
    "event": {
      "lat": 35.123,
      "lon": 15.456,
      "timestamp": "2026-03-21T12:00:00Z",
      "persons": 45,
      "vessel_type": "rubber_boat",
      "domain": "ocean_sar"
    },
    "drift": {
      "trajectory": {},
      "cone_6h": {},
      "cone_12h": {},
      "cone_24h": {},
      "metadata": {}
    },
    "public_key": "hex_encoded_ed25519_public_key"
  },
  "hash_blake3": "hex_encoded_blake3_hash",
  "signature_ed25519": "hex_encoded_ed25519_signature"
}
```

## Legal Use Guidance

This JSON packet can be printed, photographed, or stored offline. The BLAKE3 hash guarantees content integrity, while the Ed25519 signature proves the origin of the computation. This format is designed to be submitted to international courts (e.g., ICJ) as verifiable digital evidence of distress signals and predicted drift trajectories.

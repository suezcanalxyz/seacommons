# Alarm Phone image-pipeline benchmark set

This directory holds **local, operator-provided** ground-truth for the V1/V2
image-pipeline comparison (`docs/prompt.md` §11 / §12, `docs/ALARM_PHONE_IMAGE_PIPELINE_AUDIT.md` BM-1).

Third-party images are **not committed** (licensing). Each entry is a small
JSON file naming a public tweet; media is resolved live from the public
syndication CDN when the benchmark runs.

## Run

```bash
cd apps/api
python -m core.intel.backfill_alarm_phone --benchmark --limit 100
# or point at another directory:
python -m core.intel.backfill_alarm_phone --benchmark --benchmark-dir /path/to/set
```

No database is opened and nothing is written in `--benchmark` mode.

## One file per test item — `<name>.json`

```json
{
  "tweet_id": "1234567890123456789",
  "media_urls": [],
  "image_type": "map_screenshot",
  "has_coordinate_text": true,
  "has_pin": true,
  "expected_coordinate": [34.2715, 11.9423],
  "tolerance_km": 1.0
}
```

| field | meaning |
| --- | --- |
| `tweet_id` | public tweet whose media carries the map/coordinate (used if `media_urls` is empty) |
| `media_urls` | optional explicit `pbs.twimg.com` URLs, skips syndication resolution |
| `image_type` | `map_screenshot` \| `text_card` \| `infographic` \| `photo` \| `unknown` |
| `has_coordinate_text` | a printed DMS/DMM/decimal coordinate is visible in the image |
| `has_pin` | a drop-pin / circular marker is visible |
| `expected_coordinate` | `[lat, lon]` ground truth, or `null` if the image has no recoverable position |
| `tolerance_km` | how close a produced coordinate must be to count as correct |

## Reported metrics (V1 vs V2)

media retrieval recall · OCR attempt rate · coordinate recall · coordinate
precision · **false-coordinate rate** · median coordinate error km · pin
detection recall · the V1↔V2 disagreement list.

A false coordinate is worse than a missing one — V2 must never be less
precise than V1.

#!/usr/bin/env python3
"""Template relay loop: poll a personal tweet source, push new items to
SeaCommons in real time via the shared-secret ingestion endpoint.

This file is a SCAFFOLD, not a finished tool. Everything around
`fetch_new_tweets()` (the loop, dedup, signing, posting) is complete and
ready to run. `fetch_new_tweets()` itself is deliberately left as a stub —
fill it in yourself with whatever you use to read tweets (e.g. twikit,
your own account). SeaCommons's own code never calls twikit, never handles
your X credentials, and has no visibility into how you implement that
function; it only receives whatever plain-text reports you return from it.

Run with: python3 external_relay_template.py
Requires: pip install requests
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import requests

# ── Configure these ──────────────────────────────────────────────────────────
SEACOMMONS_ENDPOINT = "https://api.seacommons.org/api/v1/intel/external"
# Set this in your shell rather than hardcoding it here, so it never ends up
# committed anywhere: export EXTERNAL_INTEL_INGEST_SECRET=jsQF0TJpNC19cuFVmLFTk6rIAtQxzjpHpL7T6cVH
SHARED_SECRET = os.environ["EXTERNAL_INTEL_INGEST_SECRET"]
SOURCE_LABEL = "personal-x-relay"     # short label shown as the event's source
POLL_INTERVAL_S = 45                  # how often to check for new tweets
PUBLISH_TO_LIVE_MAP = False           # True = auto-show accepted items on the public map
STATE_FILE = Path(__file__).with_name("external_relay_state.json")


def fetch_new_tweets(since_id: str | None) -> list[dict]:
    """Return new tweets newer than `since_id`, oldest first.

    FILL THIS IN YOURSELF. Each item must be a dict with at least:
      {"id": "<tweet id, str>", "text": "<tweet text>", "url": "<tweet url>"}
    Optional: "lat", "lon" (floats) if you already know the position.

    This is the only function you need to touch. Whatever library or
    account you use to populate it is entirely your own setup — this
    script and SeaCommons's server never see it.
    """
    raise NotImplementedError("Fill in fetch_new_tweets() with your own tweet source")


# ── Everything below this line is ready to run as-is ─────────────────────────

def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_id": None, "posted_ids": []}


def _save_state(state: dict) -> None:
    # Keep the posted-ids list bounded so the state file doesn't grow forever.
    state["posted_ids"] = state["posted_ids"][-500:]
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post_to_seacommons(tweet: dict) -> bool:
    payload = {
        "source": SOURCE_LABEL,
        "source_id": str(tweet["id"]),
        "text": tweet["text"],
        "url": tweet.get("url", ""),
        "lat": tweet.get("lat"),
        "lon": tweet.get("lon"),
        "publish": PUBLISH_TO_LIVE_MAP,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-SeaCommons-Signature": _sign(SHARED_SECRET, body),
    }
    response = requests.post(SEACOMMONS_ENDPOINT, data=body, headers=headers, timeout=15)
    if response.status_code not in (200, 201):
        print(f"[relay] SeaCommons rejected {tweet['id']}: HTTP {response.status_code} {response.text[:200]}")
        return False
    print(f"[relay] posted {tweet['id']}: {response.json()}")
    return True


def run_forever() -> None:
    state = _load_state()
    print(f"[relay] starting, last_id={state['last_id']}, poll every {POLL_INTERVAL_S}s")
    while True:
        try:
            tweets = fetch_new_tweets(state["last_id"])
        except NotImplementedError:
            raise
        except Exception as exc:
            print(f"[relay] fetch failed, will retry: {exc}")
            tweets = []

        for tweet in tweets:
            tweet_id = str(tweet["id"])
            if tweet_id in state["posted_ids"]:
                continue
            if _post_to_seacommons(tweet):
                state["posted_ids"].append(tweet_id)
                state["last_id"] = tweet_id
                _save_state(state)

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    run_forever()

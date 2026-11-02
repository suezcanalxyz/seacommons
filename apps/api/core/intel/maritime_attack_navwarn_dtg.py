# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strict parser for compact NAVWARN date-time groups, not a NAVTEX collector.

Example: 'AT 282030 UTC OCT 26' means 28 October 2026 at 20:30 UTC.
The trailing 26 is the *year*, not the day. This parser deliberately
supports only this one unambiguous compact form and rejects all others.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

_DTG = re.compile(
    r"^(?:AT\s+)?(?P<day>[0-9]{2})(?P<hour>[0-9]{2})(?P<minute>[0-9]{2})"
    r"\s+UTC\s+(?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
    r"\s+(?P<year>[0-9]{2})$",
    re.IGNORECASE,
)
_MONTHS = {
    month: number for number, month in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1
    )
}


def parse_navwarn_compact_dtg(value: str) -> datetime:
    """Parse DDHHMM UTC MON YY into an aware UTC datetime or fail closed.

    The explicit 2000-2099 convention is valid for the 2026 staging corpus;
    callers must not use this parser for historical notices from 1900-1999.
    """
    if not isinstance(value, str):
        raise ValueError("invalid_navwarn_compact_dtg")
    match = _DTG.fullmatch(value.strip())
    if match is None:
        raise ValueError("invalid_navwarn_compact_dtg")
    parts = match.groupdict()
    try:
        return datetime(
            2000 + int(parts["year"]),
            _MONTHS[parts["month"].upper()],
            int(parts["day"]), int(parts["hour"]), int(parts["minute"]),
            tzinfo=timezone.utc,
        )
    except ValueError as exc:
        raise ValueError("invalid_navwarn_compact_dtg") from exc

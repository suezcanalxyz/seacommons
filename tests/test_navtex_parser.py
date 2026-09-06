from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone

import pytest


COMMON = {
    "receiver_id": "owrx-med-01",
    "physical_lineage": "central-med-rx-01",
    "observed_at": datetime(2026, 9, 6, 19, 20, tzinfo=timezone.utc),
    "frequency_hz": 518_000,
    "source_terms": "operator-permission",
    "raw_evidence_ref": "obs:navtex-raw-001",
    "area": "mediterranean",
}


def test_parses_valid_navtex_header_body_and_terminator():
    from core.radio.navtex import parse_navtex_block

    obs = parse_navtex_block(
        "ZCZC MB42\r\nGALE WARNING\r\nCENTRAL MEDITERRANEAN\r\nNNNN\r\n",
        **COMMON,
    )

    assert obs.station_id == "M"
    assert obs.subject_id == "B"
    assert obs.message_id == "42"
    assert obs.text == "GALE WARNING\nCENTRAL MEDITERRANEAN"
    assert obs.decoder_message_id.startswith("navtex_")


def test_same_navtex_block_and_context_get_same_deterministic_decoder_id():
    from core.radio.navtex import parse_navtex_block

    block = "ZCZC MA07\nNAVIGATIONAL WARNING 123\nNNNN"
    first = parse_navtex_block(block, **COMMON)
    second = parse_navtex_block(block, **COMMON)
    assert first.decoder_message_id == second.decoder_message_id


def test_explicit_decoder_message_id_is_preserved():
    from core.radio.navtex import parse_navtex_block

    obs = parse_navtex_block(
        "ZCZC MA08\nTEST MESSAGE\nNNNN",
        decoder_message_id="decoder-native-8",
        **COMMON,
    )
    assert obs.decoder_message_id == "decoder-native-8"


@pytest.mark.parametrize(
    "block,match",
    [
        ("MA42\nNO ZCZC\nNNNN", "header"),
        ("ZCZC MB42\nNO TERMINATOR", "terminator"),
        ("ZCZC M42\nBAD HEADER\nNNNN", "header"),
        ("ZCZC MB42\n\nNNNN", "body"),
    ],
)
def test_malformed_navtex_blocks_fail_closed(block, match):
    from core.radio.navtex import parse_navtex_block

    with pytest.raises(ValueError, match=match):
        parse_navtex_block(block, **COMMON)


def test_oversized_navtex_body_is_bounded_by_contract():
    from core.radio.navtex import parse_navtex_block

    obs = parse_navtex_block(f"ZCZC MB43\n{'X' * 20000}\nNNNN", **COMMON)
    assert len(obs.text) == 8192


def test_distress_wording_stays_context_without_humanitarian_or_lifecycle_authority():
    from core.radio.navtex import parse_navtex_block
    from core.radio.structured import NAVTEXObservation

    obs = parse_navtex_block(
        "ZCZC MD44\nDISTRESS TRAFFIC REPORTED IN AREA. KEEP SHARP LOOKOUT.\nNNNN",
        **COMMON,
    )
    assert "DISTRESS" in obs.text
    names = {field.name for field in fields(NAVTEXObservation)}
    assert "humanitarian" not in names
    assert "service" not in names
    assert "lifecycle" not in names
    assert "publication" not in names

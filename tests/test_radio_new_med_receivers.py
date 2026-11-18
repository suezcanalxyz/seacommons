from core.radio.catalog import catalog_entries, rank_catalog
from core.radio.multichannel_plan import configure_opt_in_channels


def test_new_barcelona_kiwi_is_a_candidate_never_an_unapproved_listener():
    matches = [r for r in catalog_entries() if r.receiver_id == "barcelona_ea3hru_hf_candidate"]
    assert len(matches) == 1
    row = matches[0]
    assert row.country == "ES"
    assert abs(row.lat - 41.41136) < 0.0001
    assert row.activation_status == "review_required"
    assert row.terms_status == "unknown"
    assert row.to_descriptor(8_414_500, "usb").enabled is False
    assert row.to_descriptor(8_414_500, "usb").terms_status == "unknown"
    assert row not in [x for x in rank_catalog("central_med", frequency_hz=8_414_500)
                       if x.activation_status == "eligible"]
    try:
        configure_opt_in_channels([row.to_descriptor(8_414_500, "usb")],
            '[{"receiver_id":"barcelona_ea3hru_hf_candidate","frequency_hz":8414500,"channel_kind":"dsc","operator_authorized":true}]')
    except ValueError as exc:
        assert "non-authorized" in str(exc)
    else:
        raise AssertionError("receiver must not be auto-authorized")

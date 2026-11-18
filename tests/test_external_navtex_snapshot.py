from unittest.mock import patch

from core.radio import external_navtex as navtex


def test_public_navtex_snapshot_preserves_secondary_provenance_and_caches():
    with patch.object(navtex, "_cache_next_request", 0.0), \
         patch.object(navtex, "_cache_rows", []), \
         patch.object(navtex, "_cache_fetched_at", None), \
         patch.object(navtex, "_cache_error", None), \
         patch.object(navtex, "fetch_navtex_messages",
                      return_value=[navtex.normalize_navtex_message({"id": "test-123"})]) as fetch:
        first = navtex.public_navtex_snapshot()
        second = navtex.public_navtex_snapshot()
        assert first["state"] == "live"
        assert first["independent_rf_reception"] is False
        assert first["source_class"] == "secondary_maritime_safety_information"
        assert first["messages"][0]["is_dsc_decode"] is False
        assert second["messages"] == first["messages"]
        fetch.assert_called_once_with(navarea="III", limit=50)


def test_public_navtex_snapshot_marks_provider_failure_and_never_invents_evidence():
    with patch.object(navtex, "_cache_next_request", 0.0), \
         patch.object(navtex, "_cache_rows", []), \
         patch.object(navtex, "_cache_fetched_at", None), \
         patch.object(navtex, "_cache_error", None), \
         patch.object(navtex, "fetch_navtex_messages", side_effect=OSError("upstream failed")):
        snapshot = navtex.public_navtex_snapshot()
        assert snapshot["state"] == "degraded"
        assert snapshot["messages"] == []
        assert snapshot["independent_rf_reception"] is False

from core.radio.catalog import catalog_entries, rank_catalog


def test_catalog_contains_only_approved_free_open_or_public_monitor_networks():
    rows = catalog_entries()
    families = {row.network_family for row in rows}
    assert {"kiwisdr", "openwebrx"} <= families
    assert "globaltuners" not in families
    assert all(row.terms_status == "allowed" for row in rows if row.activation_status == "eligible")


def test_catania_openwebrx_is_prioritized_for_central_mediterranean():
    ranked = rank_catalog("central_med", frequency_hz=2_187_500)
    ids = [row.receiver_id for row in ranked[:6]]
    assert "catania_openwebrx" in ids
    catania = next(row for row in ranked if row.receiver_id == "catania_openwebrx")
    assert catania.network_family == "openwebrx"
    assert catania.license_class == "open_source"
    assert catania.supports_frequency(2_187_500)


def test_rank_catalog_prefers_geographic_relevance_and_deduplicates_lineage():
    ranked = rank_catalog("central_med", frequency_hz=2_187_500)
    lineages = [row.physical_lineage for row in ranked]
    assert len(lineages) == len(set(lineages))
    assert ranked[0].priority_score >= ranked[-1].priority_score
    assert all(row.supports_frequency(2_187_500) for row in ranked)


def test_catalog_descriptors_are_runtime_safe_and_monitor_only():
    ranked = rank_catalog("central_med", frequency_hz=2_187_500, limit=20)
    descriptors = [row.to_descriptor(2_187_500, "usb") for row in ranked if row.activation_status == "eligible"]
    assert descriptors
    assert all(row.channel_kind == "monitor" for row in descriptors)
    assert all(row.frequency_hz == 2_187_500 for row in descriptors)
    assert all(row.terms_status == "allowed" for row in descriptors)

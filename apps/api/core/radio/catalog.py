from __future__ import annotations

from dataclasses import dataclass, replace
from math import asin, cos, radians, sin, sqrt

from core.radio.provider import ReceiverCapability
from core.radio.registry import ReceiverDescriptor

_HF_CAP = (ReceiverCapability(10_000, 30_000_000, ("am", "usb", "lsb", "nbfm")),)
_KIWI_TERMS = "Public Internet receiver listed by its operator in the KiwiSDR public receiver ecosystem; monitor-only metadata, no raw audio storage."
_OWRX_TERMS = "Public OpenWebRX receiver endpoint operated for browser access; OpenWebRX is AGPL-3.0 software; monitor-only metadata, no raw audio storage."
_ZONE_CENTERS = {
    "central_med": (35.9, 14.4),
    "sicily_channel": (36.3, 13.2),
    "malta": (35.9, 14.4),
    "tunisia_north": (36.8, 10.2),
    "ionian": (37.5, 19.5),
}


@dataclass(frozen=True)
class ReceiverCatalogEntry:
    receiver_id: str
    public_label: str
    network_family: str
    endpoint: str
    physical_lineage: str
    lat: float
    lon: float
    country: str
    license_class: str
    terms_status: str
    activation_status: str
    source_terms: str
    capabilities: tuple[ReceiverCapability, ...] = _HF_CAP
    priority_score: float = 0.0

    def supports_frequency(self, frequency_hz: int) -> bool:
        return any(cap.frequency_min_hz <= frequency_hz <= cap.frequency_max_hz for cap in self.capabilities)

    def to_descriptor(self, frequency_hz: int, mode: str) -> ReceiverDescriptor:
        return ReceiverDescriptor(
            receiver_id=self.receiver_id,
            provider=self.network_family,
            frontend_url=self.endpoint,
            physical_lineage=self.physical_lineage,
            enabled=self.activation_status == "eligible",
            terms_status=self.terms_status,
            source_terms=self.source_terms,
            capabilities=self.capabilities,
            public_label=self.public_label,
            channel_kind="monitor",
            frequency_hz=frequency_hz,
            mode=mode,
        )


def _entry(receiver_id, label, family, endpoint, lineage, lat, lon, country, *, license_class="public_access"):
    return ReceiverCatalogEntry(
        receiver_id=receiver_id, public_label=label, network_family=family,
        endpoint=endpoint, physical_lineage=lineage, lat=lat, lon=lon,
        country=country, license_class=license_class, terms_status="allowed",
        activation_status="eligible", source_terms=_OWRX_TERMS if family == "openwebrx" else _KIWI_TERMS,
    )


def catalog_entries() -> tuple[ReceiverCatalogEntry, ...]:
    return (
        _entry("catania_openwebrx", "Catania OpenWebRX HF monitor", "openwebrx", "http://arascatania.ns0.it:8073", "catania_iw9gtr_openwebrx", 37.50, 15.09, "IT", license_class="open_source"),
        _entry("cagliari_hf_monitor", "Cagliari HF DSC monitor", "kiwisdr", "http://sergiocorda.synology.me:28073", "cagliari_1hs1322_kiwisdr", 39.22, 9.12, "IT"),
        _entry("salerno_hf_monitor", "Salerno HF DSC monitor", "kiwisdr", "http://21443.proxy.kiwisdr.com", "salerno_ik8sut_kiwisdr", 40.68819, 14.77103, "IT"),
        _entry("trecastelli_hf_monitor", "Trecastelli HF DSC monitor", "kiwisdr", "http://iw2nke.ddns.net:8073", "trecastelli_iw2nke_kiwisdr", 43.662, 13.137, "IT"),
        _entry("san_marino_hf_monitor", "San Marino HF DSC monitor", "kiwisdr", "http://22416.proxy.kiwisdr.com", "san_marino_kiwisdr", 43.938063, 12.445187, "SM"),
        _entry("slovenia_hf_monitor", "Slovenia HF DSC monitor", "kiwisdr", "http://188.159.246.61:8073", "slovenia_s59gcd_kiwisdr", 46.183065, 15.208332, "SI"),
        _entry("zakynthos_hf_monitor", "Zakynthos HF DSC monitor", "kiwisdr", "http://sv8rv.dyndns.org:8073", "zakynthos_sv8rv_kiwisdr", 37.783103, 20.896453, "GR"),
        _entry("thessaloniki_hf_monitor", "Thessaloniki HF DSC monitor", "kiwisdr", "http://elektrongr.ddns.net:8073", "thessaloniki_elektron_kiwisdr", 40.623552, 22.969851, "GR"),
        _entry("edessa_hf_monitor", "Edessa HF DSC monitor", "kiwisdr", "http://21900.proxy.kiwisdr.com", "edessa_sv2csn_kiwisdr", 40.808527, 22.073561, "GR"),
        _entry("mallorca_hf_monitor", "Mallorca HF DSC monitor", "kiwisdr", "http://37.10.74.235:8073", "mallorca_alcudia_kiwisdr", 39.8353, 3.096, "ES"),
        _entry("rome_hf_monitor", "Rome HF DSC monitor", "kiwisdr", "http://kiwisdr-iz0ina.ns0.it:8073", "rome_iz0ina_kiwisdr", 41.90, 12.50, "IT"),
        _entry("milano_hf_monitor", "Milano HF DSC monitor", "kiwisdr", "http://milano1602.dyndns.org:8073", "milano_1602_kiwisdr", 45.480424, 9.186175, "IT"),
        _entry("cassine_hf_monitor", "Cassine HF DSC monitor", "kiwisdr", "http://kiwisdr.briata.org:8073", "cassine_i1cra_kiwisdr", 44.778962, 8.531099, "IT"),
        _entry("botticino_hf_monitor", "Botticino HF DSC monitor", "kiwisdr", "http://ik2biy.proxy.kiwisdr.com", "botticino_ik2biy_kiwisdr", 45.709315, 10.212806, "IT"),
        _entry("heimiswil_hf_monitor", "Heimiswil HF DSC monitor", "kiwisdr", "http://hb9cwk.internet-box.ch:8073", "heimiswil_hb9cwk_kiwisdr", 47.057209, 7.648012, "CH"),
        _entry("bad_ragaz_hf_monitor", "Bad Ragaz HF DSC monitor", "kiwisdr", "http://sdr-badragaz.proxy.kiwisdr.com", "bad_ragaz_kiwisdr", 47.021458, 9.481197, "CH"),
    )


def _distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    dlat, dlon = radians(b_lat-a_lat), radians(b_lon-a_lon)
    a = sin(dlat/2)**2 + cos(radians(a_lat))*cos(radians(b_lat))*sin(dlon/2)**2
    return 6371.0 * 2 * asin(sqrt(a))


def rank_catalog(zone: str, *, frequency_hz: int, limit: int | None = None) -> tuple[ReceiverCatalogEntry, ...]:
    center = _ZONE_CENTERS.get(zone, _ZONE_CENTERS["central_med"])
    seen: set[str] = set(); ranked: list[ReceiverCatalogEntry] = []
    for row in catalog_entries():
        if row.physical_lineage in seen or not row.supports_frequency(frequency_hz):
            continue
        seen.add(row.physical_lineage)
        distance = _distance_km(center[0], center[1], row.lat, row.lon)
        open_bonus = 120.0 if row.license_class == "open_source" else 0.0
        central_bonus = 180.0 if row.country in {"IT", "MT", "TN"} else 0.0
        score = max(0.0, 1200.0 - distance) + open_bonus + central_bonus
        ranked.append(replace(row, priority_score=round(score, 2)))
    ranked.sort(key=lambda row: (-row.priority_score, row.receiver_id))
    return tuple(ranked[:limit] if limit is not None else ranked)

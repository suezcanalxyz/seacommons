from __future__ import annotations

from core.radio.provider import ReceiverCapability
from core.radio.registry import ReceiverDescriptor

_TERMS = (
    "Public Internet receiver explicitly listed by its operator in the official KiwiSDR public directory at rx.kiwisdr.com; "
    "SeaCommons uses monitor-only signal metadata and stores no raw audio."
)
_CAP = (ReceiverCapability(10_000, 30_000_000, ("am", "usb", "lsb", "nbfm")),)
_FREQ = 2_187_500


def _rx(receiver_id: str, label: str, url: str, lineage: str) -> ReceiverDescriptor:
    return ReceiverDescriptor(
        receiver_id=receiver_id,
        provider="kiwisdr",
        frontend_url=url,
        physical_lineage=lineage,
        enabled=True,
        terms_status="allowed",
        source_terms=_TERMS,
        capabilities=_CAP,
        public_label=label,
        channel_kind="monitor",
        frequency_hz=_FREQ,
        mode="usb",
    )


def public_receiver_pool() -> tuple[ReceiverDescriptor, ...]:
    """Curated public HF receiver pool useful for Mediterranean DSC monitoring."""
    return (
        _rx("rome_hf_monitor", "Rome HF DSC monitor", "http://kiwisdr-iz0ina.ns0.it:8073", "rome_iz0ina_kiwisdr"),
        _rx("cagliari_hf_monitor", "Cagliari HF DSC monitor", "http://sergiocorda.synology.me:28073", "cagliari_1hs1322_kiwisdr"),
        _rx("trecastelli_hf_monitor", "Trecastelli HF DSC monitor", "http://iw2nke.ddns.net:8073", "trecastelli_iw2nke_kiwisdr"),
        _rx("botticino_hf_monitor", "Botticino HF DSC monitor", "http://ik2biy.proxy.kiwisdr.com", "botticino_ik2biy_kiwisdr"),
        _rx("milano_hf_monitor", "Milano HF DSC monitor", "http://milano1602.dyndns.org:8073", "milano_1602_kiwisdr"),
        _rx("cassine_hf_monitor", "Cassine HF DSC monitor", "http://kiwisdr.briata.org:8073", "cassine_i1cra_kiwisdr"),
        _rx("heimiswil_hf_monitor", "Heimiswil HF DSC monitor", "http://hb9cwk.internet-box.ch:8073", "heimiswil_hb9cwk_kiwisdr"),
        _rx("bad_ragaz_hf_monitor", "Bad Ragaz HF DSC monitor", "http://sdr-badragaz.proxy.kiwisdr.com", "bad_ragaz_kiwisdr"),
        _rx("salerno_hf_monitor", "Salerno HF DSC monitor", "http://21443.proxy.kiwisdr.com", "salerno_ik8sut_kiwisdr"),
        _rx("san_marino_hf_monitor", "San Marino HF DSC monitor", "http://22416.proxy.kiwisdr.com", "san_marino_kiwisdr"),
        _rx("slovenia_hf_monitor", "Slovenia HF DSC monitor", "http://188.159.246.61:8073", "slovenia_s59gcd_kiwisdr"),
        _rx("edessa_hf_monitor", "Edessa HF DSC monitor", "http://21900.proxy.kiwisdr.com", "edessa_sv2csn_kiwisdr"),
        _rx("thessaloniki_hf_monitor", "Thessaloniki HF DSC monitor", "http://elektrongr.ddns.net:8073", "thessaloniki_elektron_kiwisdr"),
        _rx("zakynthos_hf_monitor", "Zakynthos HF DSC monitor", "http://sv8rv.dyndns.org:8073", "zakynthos_sv8rv_kiwisdr"),
        _rx("mallorca_hf_monitor", "Mallorca HF DSC monitor", "http://37.10.74.235:8073", "mallorca_alcudia_kiwisdr"),
    )

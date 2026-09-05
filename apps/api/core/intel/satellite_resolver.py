"""Free satellite observation discovery for temporal OSINT reconstruction."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Literal

import httpx

from core.intel.lifecycle import parse_utc
from core.intel.satellite_observation import SatelliteObservation

COPERNICUS_STAC_URL = "https://stac.dataspace.copernicus.eu/v1"
DEFAULT_COPERNICUS_COLLECTIONS = [
    "sentinel-1-grd",
    "sentinel-2-l2a",
    "sentinel-3-olci-2-wfr-nrt",
]


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]
    return f"sat:{digest}"


def _acquired_ms(observation: SatelliteObservation) -> float:
    parsed = parse_utc(observation.acquisition_time)
    if parsed is None:
        return float("inf")
    return parsed.timestamp()


def select_temporal_observations(
    observations: Iterable[SatelliteObservation],
    event_time: datetime,
    direction: Literal["reverse", "nearest", "forward"],
) -> list[SatelliteObservation]:
    event_ts = event_time.astimezone(timezone.utc).timestamp()
    candidates = []
    for observation in observations:
        acquired = parse_utc(observation.acquisition_time)
        if acquired is None:
            continue
        delta = acquired.timestamp() - event_ts
        if direction == "reverse" and delta > 0:
            continue
        if direction == "forward" and delta < 0:
            continue
        candidates.append(replace(
            observation,
            temporal_relation=direction,
            temporal_delta_s=delta,
        ))
    if direction == "reverse":
        candidates.sort(key=_acquired_ms, reverse=True)
    elif direction == "forward":
        candidates.sort(key=_acquired_ms)
    else:
        candidates.sort(key=lambda item: abs(item.temporal_delta_s))
        candidates = candidates[:1]
    return candidates


_VIIRS_LAYERS = (
    ("VIIRS NOAA-20", "VIIRS_NOAA20_CorrectedReflectance_TrueColor"),
    ("VIIRS NOAA-21", "VIIRS_NOAA21_CorrectedReflectance_TrueColor"),
    ("VIIRS Suomi-NPP", "VIIRS_SNPP_CorrectedReflectance_TrueColor"),
)


def viirs_daily_observations(
    *, incident_id: str, lat: float, lon: float, day: date,
) -> list[SatelliteObservation]:
    acquired = datetime.combine(day, time.min, tzinfo=timezone.utc).isoformat()
    day_text = day.isoformat()
    bbox = [lon - 0.1, lat - 0.1, lon + 0.1, lat + 0.1]
    observations = []
    for mission, layer in _VIIRS_LAYERS:
        tile = (
            f"https://gibs-a.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/"
            f"default/{day_text}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.jpg"
        )
        observations.append(SatelliteObservation(
            observation_id=_stable_id(incident_id, "nasa_gibs", layer, day_text),
            incident_id=incident_id,
            provider="nasa_gibs",
            mission=mission,
            product_id=f"{layer}:{day_text}",
            acquisition_time=acquired,
            discovered_at=datetime.now(timezone.utc).isoformat(),
            footprint=None,
            bbox=bbox,
            sensor_type="optical_context",
            temporal_relation="nearest",
            temporal_delta_s=0,
            asset_ref=tile,
            source_url="https://gibs.earthdata.nasa.gov/",
            provenance={"layer": layer, "temporal_precision": "day"},
            evidence_status="contextual",
        ))
    return observations


def _mission_for_feature(feature: dict, collection: str) -> tuple[str, str]:
    platform = str((feature.get("properties") or {}).get("platform") or "").lower()
    token = f"{collection} {platform}"
    if "sentinel-1" in token:
        return "Sentinel-1", "sar"
    if "sentinel-2" in token:
        return "Sentinel-2", "optical"
    if "sentinel-3" in token:
        return "Sentinel-3", "ocean_context"
    return collection or "Copernicus", "satellite"


def _asset_href(feature: dict) -> str:
    assets = feature.get("assets") or {}
    for key in ("thumbnail", "preview", "visual", "rendered_preview"):
        href = (assets.get(key) or {}).get("href")
        if href:
            return str(href)
    for asset in assets.values():
        if isinstance(asset, dict) and asset.get("href"):
            return str(asset["href"])
    return ""


def _self_href(feature: dict) -> str:
    for link in feature.get("links") or []:
        if link.get("rel") == "self" and link.get("href"):
            return str(link["href"])
    return ""


class CopernicusSTACProvider:
    def __init__(self, *, client=None, base_url: str = COPERNICUS_STAC_URL) -> None:
        self.client = client or httpx.Client(timeout=15.0)
        self.base_url = base_url.rstrip("/")

    def search(
        self,
        *,
        incident_id: str,
        bbox: list[float],
        start: datetime,
        end: datetime,
        collections: list[str],
        limit: int = 50,
    ) -> list[SatelliteObservation]:
        body = {
            "bbox": bbox,
            "datetime": f"{_iso(start)}/{_iso(end)}",
            "collections": collections,
            "limit": limit,
        }
        response = self.client.post(f"{self.base_url}/search", json=body)
        response.raise_for_status()
        features = response.json().get("features") or []
        return [
            self._normalize_feature(incident_id=incident_id, feature=feature)
            for feature in features
            if ((feature.get("properties") or {}).get("datetime") or (feature.get("properties") or {}).get("start_datetime"))
        ]
    def _normalize_feature(
        self, *, incident_id: str, feature: dict,
    ) -> SatelliteObservation:
        props = feature.get("properties") or {}
        product_id = str(feature.get("id") or "unknown")
        collection = str(feature.get("collection") or "")
        mission, sensor_type = _mission_for_feature(feature, collection)
        acquired = str(props.get("datetime") or props.get("start_datetime"))
        cloud = props.get("eo:cloud_cover")
        gsd = props.get("gsd")
        polarisation = props.get("sar:polarizations")
        return SatelliteObservation(
            observation_id=_stable_id(incident_id, "copernicus_dataspace", product_id),
            incident_id=incident_id,
            provider="copernicus_dataspace",
            mission=mission,
            product_id=product_id,
            acquisition_time=acquired,
            discovered_at=datetime.now(timezone.utc).isoformat(),
            footprint=feature.get("geometry"),
            bbox=feature.get("bbox"),
            sensor_type=sensor_type,
            temporal_relation="nearest",
            temporal_delta_s=0,
            asset_ref=_asset_href(feature),
            source_url=_self_href(feature),
            provenance={"stac_collection": collection, "platform": props.get("platform")},
            resolution_m=float(gsd) if gsd is not None else None,
            cloud_cover=float(cloud) if cloud is not None else None,
            polarisation=list(polarisation) if isinstance(polarisation, list) else None,
            evidence_status="contextual",
        )


def resolve_for_incident(
    *,
    incident_id: str,
    lat: float,
    lon: float,
    event_time: datetime,
    direction: Literal["reverse", "nearest", "forward"],
    provider=None,
    include_viirs: bool = True,
    radius_deg: float = 0.2,
    now: datetime | None = None,
) -> list[SatelliteObservation]:
    event_time = event_time.astimezone(timezone.utc)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    bbox = [round(value, 6) for value in (lon - radius_deg, lat - radius_deg, lon + radius_deg, lat + radius_deg)]
    provider = provider or CopernicusSTACProvider()

    if direction == "reverse":
        start, end = event_time - timedelta(days=7), event_time
    elif direction == "forward":
        start = event_time
        end = min(max(event_time, now), event_time + timedelta(days=7))
    else:
        start = event_time - timedelta(days=3)
        end = min(event_time + timedelta(days=3), max(event_time, now))

    observations = provider.search(
        incident_id=incident_id,
        bbox=bbox,
        start=start,
        end=end,
        collections=list(DEFAULT_COPERNICUS_COLLECTIONS),
    )
    if include_viirs:
        cursor = start.date()
        while cursor <= end.date():
            observations.extend(viirs_daily_observations(
                incident_id=incident_id, lat=lat, lon=lon, day=cursor,
            ))
            cursor += timedelta(days=1)

    selected = select_temporal_observations(observations, event_time, direction)
    return selected

#!/usr/bin/env python3
"""Discover Sentinel-1 products in public PLAY and review calibrated SAR rasters."""
import argparse
from datetime import datetime, timezone
import json
import math
from hashlib import file_digest
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

PLAY_API = "https://play.seacommons.org/api/v1/play"


def utc(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Expected a timestamp with timezone")
    return timestamp.astimezone(timezone.utc)


def load_json(path):
    with urlopen(f"{PLAY_API}/{path}", timeout=25) as response:
        return json.load(response)


def case_timeline(case_id):
    return load_json(f"incidents/{quote(case_id, safe='')}/timeline")


def scenes(case_id, timeline):
    return sorted([
        {
            "incident_id": timeline.get("incident_id") or case_id,
            "observation_id": item["id"],
            "acquired_at": item["at"],
            "product_id": props["product_id"],
            "source_url": props.get("source_url"),
            "pixel_spacing_m": props.get("resolution_m"),
            "polarisation": props.get("polarisation"),
            "delta_seconds": props.get("temporal_delta_s"),
        }
        for item in timeline.get("timeline", [])
        if item.get("type") == "satellite" and item.get("source") == "copernicus_dataspace"
        and (props := item.get("properties", {})).get("mission") == "Sentinel-1"
        and "GRD" in props.get("product_id", "")
        and item.get("at")
    ], key=lambda scene: (
        abs(scene["delta_seconds"]) if scene["delta_seconds"] is not None else math.inf,
        scene["acquired_at"],
    ))


def nearby_ais_fixes(timeline, acquired_at, lon, lat):
    """Return nearby published observations as review context without inferring identity."""
    acquired = utc(acquired_at)
    matches = []
    for vessel in (timeline.get("voyage_evidence") or {}).get("vessels", []):
        closest = None
        for fix in vessel.get("track_points", []):
            try:
                delta = (utc(fix["at"]) - acquired).total_seconds()
                fix_lat, fix_lon = float(fix["lat"]), float(fix["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if abs(delta) > 300 or not (-90 <= fix_lat <= 90 and -180 <= fix_lon <= 180):
                continue
            haversine = math.sin(math.radians(fix_lat - lat) / 2) ** 2 + (
                math.cos(math.radians(lat)) * math.cos(math.radians(fix_lat))
                * math.sin(math.radians(fix_lon - lon) / 2) ** 2
            )
            metres = 12_742_000 * math.asin(math.sqrt(min(haversine, 1)))
            if metres > 1_000:
                continue
            rank = (metres, abs(delta))
            if closest is None or rank < closest[0]:
                closest = (rank, {"mmsi": vessel.get("mmsi"), "at": fix["at"],
                                  "coordinates": [fix_lon, fix_lat], "time_offset_seconds": delta,
                                  "distance_m": round(metres, 1)})
        if closest:
            matches.append(closest[1])
    return sorted(matches, key=lambda fix: fix["distance_m"])


def analyze(args):
    import numpy as np
    from PIL import Image
    from osgeo import gdal, osr
    from scipy.ndimage import label, maximum_position, uniform_filter

    timeline = case_timeline(args.case_id)
    scene = next((record for record in scenes(args.case_id, timeline) if record["product_id"] == args.product), None)
    if scene is None:
        raise ValueError("The selected Sentinel-1 product is missing from the historical PLAY case")
    gdal.UseExceptions()
    dataset = gdal.Open(args.raster, gdal.GA_ReadOnly)
    source_crs = dataset.GetSpatialRef()
    affine = dataset.GetGeoTransform(can_return_null=True)
    if dataset.RasterCount != 1 or source_crs is None or affine is None:
        raise ValueError("Expected a georeferenced single-band calibrated SAR GeoTIFF")
    if dataset.RasterXSize * dataset.RasterYSize > 4_000_000:
        raise ValueError("Subset the calibrated raster to a review area under four million pixels")
    band = dataset.GetRasterBand(1)
    values = band.ReadAsArray().astype("float64")
    values[band.GetMaskBand().ReadAsArray() == 0] = np.nan
    source_crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(4326)
    wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_wgs84 = osr.CoordinateTransformation(source_crs, wgs84)

    def lonlat(col, row):
        x, y = gdal.ApplyGeoTransform(affine, float(col), float(row))
        longitude, latitude, *_ = to_wgs84.TransformPoint(x, y)
        return [longitude, latitude]

    valid = np.isfinite(values)
    if args.scale == "linear":
        valid &= values > 0
        values[valid] = 10 * np.log10(values[valid])
    if not valid.any():
        raise ValueError("The raster contains no valid backscatter")
    data = np.where(valid, values, 0.0)

    # Estimate the local background in a square ring, excluding nearby target pixels.
    def ring_sum(array):
        return uniform_filter(array, size=31, mode="constant") * 31**2 - (
            uniform_filter(array, size=9, mode="constant") * 9**2
        )

    neighbours = ring_sum(valid.astype("float64"))
    divisor = np.maximum(neighbours, 1)
    mean = ring_sum(data) / divisor
    variance = np.maximum(ring_sum(data**2) / divisor - mean**2, 0)
    score = (data - mean) / np.maximum(np.sqrt(variance), 1)
    mask = valid & (neighbours >= 0.8 * (31**2 - 9**2)) & (score >= args.threshold)
    groups, group_count = label(mask, structure=np.ones((3, 3)))
    ids = np.arange(1, group_count + 1)
    areas = np.bincount(groups.ravel(), minlength=group_count + 1)[1:]
    ids = ids[areas >= 2]
    peaks = maximum_position(score, groups, ids.tolist()) if ids.size else []
    ranked = sorted(peaks, key=lambda point: score[point], reverse=True)[:args.max_candidates]

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    features = []
    for index, (row, col) in enumerate(ranked, 1):
        top, left = max(0, row - 48), max(0, col - 48)
        crop = values[top:row + 49, left:col + 49]
        low, high = np.nanpercentile(crop, [2, 99])
        preview = np.clip((crop - low) / max(high - low, 1) * 255, 0, 255)
        image = f"return-{index:02}.png"
        Image.fromarray(np.nan_to_num(preview).astype("uint8")).save(output / image)
        lon, lat = lonlat(col + 0.5, row + 0.5)
        corners = [lonlat(x, y) for x, y in (
            (left, top), (left + crop.shape[1], top),
            (left + crop.shape[1], top + crop.shape[0]), (left, top + crop.shape[0]),
        )]
        crop_path = f"return-{index:02}.tif"
        gdal.Translate(str(output / crop_path), dataset, srcWin=[left, top, crop.shape[1], crop.shape[0]]).FlushCache()
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "status": "unreviewed_radar_return",
                "identity": None,
                "local_contrast_score": round(float(score[row, col]), 2),
                "preview": image,
                "preview_corners": corners,
                "geotiff": crop_path,
                "nearby_published_ais_fixes": nearby_ais_fixes(timeline, scene["acquired_at"], lon, lat),
            },
        })
    with open(args.raster, "rb") as file:
        raster_hash = file_digest(file, "sha256").hexdigest()
    result = {
        "type": "FeatureCollection",
        "scene": scene,
        "analysis": {"method": "local_backscatter_outlier_v1", "threshold": args.threshold,
                     "input_scale": args.scale, "candidate_limit": args.max_candidates,
                     "input_raster_sha256": raster_hash,
                     "product_attribution": "operator_supplied_raster",
                     "ais_review_window_seconds": 300, "ais_review_radius_m": 1000,
                     "returns_before_limit": len(peaks)},
        "features": features,
    }
    (output / "radar-returns.geojson").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"{len(features)} unreviewed radar returns in {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("scenes", help="List historical Sentinel-1 products from a PLAY dossier")
    discover.add_argument("case_id", nargs="+")
    detect = commands.add_parser("detect", help="Review a prepared, single-band Sentinel-1 GeoTIFF")
    detect.add_argument("case_id")
    detect.add_argument("product")
    detect.add_argument("raster")
    detect.add_argument("output")
    detect.add_argument("--scale", choices=["linear", "db"], required=True)
    detect.add_argument("--threshold", type=float, default=5)
    detect.add_argument("--max-candidates", type=int, default=30)
    args = parser.parse_args()
    if args.command == "scenes":
        print(json.dumps([record for case_id in args.case_id for record in scenes(case_id, case_timeline(case_id))], indent=2))
    else:
        if not 0 < args.threshold < float("inf") or not 1 <= args.max_candidates <= 100:
            parser.error("Use a positive finite threshold and a candidate limit from 1 to 100")
        analyze(args)


if __name__ == "__main__":
    main()

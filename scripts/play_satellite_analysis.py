#!/usr/bin/env python3
"""Discover Sentinel-1 products in public PLAY and review calibrated SAR rasters."""
import argparse
from datetime import datetime, timezone
import json
import math
from hashlib import file_digest, sha256
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

PLAY_API = "https://play.seacommons.org/api/v1/play"
RTC_COLLECTION = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items"


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


def distance_m(lon, lat, other_lon, other_lat):
    haversine = math.sin(math.radians(other_lat - lat) / 2) ** 2 + (
        math.cos(math.radians(lat)) * math.cos(math.radians(other_lat))
        * math.sin(math.radians(other_lon - lon) / 2) ** 2
    )
    return 12_742_000 * math.asin(math.sqrt(min(haversine, 1)))


def nearby_case_sources(timeline, acquired_at, lon, lat):
    """Find public case records with their own times and point geometry."""
    acquired = utc(acquired_at)
    matches = []
    for item in timeline.get("timeline", []):
        if item.get("type") not in {"radio", "radio_observation", "report", "update"}:
            continue
        geometry = item.get("geometry") or {}
        if geometry.get("type") != "Point":
            continue
        try:
            delta = (utc(item["at"]) - acquired).total_seconds()
            other_lon, other_lat = map(float, geometry["coordinates"][:2])
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if abs(delta) > 3600 or not (-180 <= other_lon <= 180 and -90 <= other_lat <= 90):
            continue
        metres = distance_m(lon, lat, other_lon, other_lat)
        if metres <= 5_000:
            props = item.get("properties") or {}
            matches.append({
                "id": item.get("id"), "type": item["type"], "source": item.get("source"),
                "at": item["at"], "time_offset_seconds": delta, "distance_m": round(metres, 1),
                "source_url": props.get("source_url") or props.get("url"),
                "recorded_association": props.get("match_status"),
            })
    return sorted(matches, key=lambda item: abs(item["time_offset_seconds"]))[:12]


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
            metres = distance_m(lon, lat, fix_lon, fix_lat)
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


def rasterize_land_mask(dataset, path):
    """Rasterize clipped land polygons onto the exact input radar grid."""
    from osgeo import gdal, ogr, osr

    vector_path = str(Path(path).resolve())
    if vector_path.lower().endswith(".zip"):
        vector_path = f"/vsizip/{vector_path}"
    vector = gdal.OpenEx(vector_path, gdal.OF_VECTOR)
    layer = vector.GetLayer(0)
    land_crs = layer.GetSpatialRef()
    if land_crs is None:
        raise ValueError("Expected land polygons with a declared CRS")
    radar_crs = dataset.GetSpatialRef()
    for crs in (land_crs, radar_crs):
        crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_land = osr.CoordinateTransformation(radar_crs, land_crs)
    to_radar = osr.CoordinateTransformation(land_crs, radar_crs)
    width, height = dataset.RasterXSize, dataset.RasterYSize
    affine = dataset.GetGeoTransform()
    # Sample the edges rather than just the corners when projecting the bounds.
    points = []
    for step in range(21):
        col, row = width * step / 20, height * step / 20
        for x, y in ((col, 0), (col, height), (0, row), (width, row)):
            points.append(to_land.TransformPoint(*gdal.ApplyGeoTransform(affine, x, y)))
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    if land_crs.IsGeographic() and east - west > 180:
        raise ValueError("Subset the radar scene to one side of the antimeridian")
    clip = ogr.CreateGeometryFromWkt(
        f"POLYGON (({west} {south}, {east} {south}, {east} {north}, "
        f"{west} {north}, {west} {south}))"
    )
    layer.SetSpatialFilter(clip)
    memory = ogr.GetDriverByName("Memory").CreateDataSource("")
    local = memory.CreateLayer("land", radar_crs)
    for row in layer:
        geometry = row.GetGeometryRef()
        if geometry is None:
            continue
        clipped = geometry.Intersection(clip)
        if clipped.IsEmpty():
            continue
        clipped.Transform(to_radar)
        feature = ogr.Feature(local.GetLayerDefn())
        feature.SetGeometry(clipped)
        local.CreateFeature(feature)
    mask = gdal.GetDriverByName("MEM").Create("", width, height, 1, gdal.GDT_Byte)
    mask.SetGeoTransform(affine)
    mask.SetSpatialRef(radar_crs)
    band = mask.GetRasterBand(1)
    band.Fill(1)
    gdal.RasterizeLayer(mask, [1], local, burn_values=[0])
    return band.ReadAsArray() == 1


def analyze(args):
    import numpy as np
    from PIL import Image
    from osgeo import gdal, osr
    from scipy.ndimage import label, maximum_position, minimum_filter, uniform_filter

    if args.case_id:
        timeline = case_timeline(args.case_id)
        scene = next((record for record in scenes(args.case_id, timeline) if record["product_id"] == args.product), None)
        if scene is None:
            raise ValueError("The selected Sentinel-1 product is missing from the historical PLAY case")
    else:
        url = f"{RTC_COLLECTION}/{quote(args.product, safe='')}"
        with urlopen(url, timeout=25) as response:
            item = json.load(response)
        if item.get("id") != args.product or item.get("collection") != "sentinel-1-rtc":
            raise ValueError("Expected an exact Sentinel-1 RTC catalog item")
        timeline = {}
        scene = {
            "incident_id": None, "product_id": item["id"],
            "acquired_at": item["properties"]["datetime"],
            "source_url": url, "purpose": "historical_sensor_validation",
        }
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
    water_mask = getattr(args, "water_mask", None)
    land_polygons = getattr(args, "land_polygons", None)
    water_source = water_mask or land_polygons
    if water_mask:
        water = gdal.Open(water_mask, gdal.GA_ReadOnly)
        if (water.RasterCount != 1 or water.RasterXSize != dataset.RasterXSize
                or water.RasterYSize != dataset.RasterYSize
                or water.GetGeoTransform(can_return_null=True) != affine
                or water.GetSpatialRef() is None
                or not bool(water.GetSpatialRef().IsSame(dataset.GetSpatialRef()))):
            raise ValueError("The water mask must have the same CRS, extent and pixel grid as the radar raster")
        mask_band = water.GetRasterBand(1)
        valid &= (mask_band.ReadAsArray() == 1) & (mask_band.GetMaskBand().ReadAsArray() != 0)
    elif land_polygons:
        valid &= rasterize_land_mask(dataset, land_polygons)
    if args.scale == "linear":
        valid &= values > 0
        values[valid] = 10 * np.log10(values[valid])
    if not valid.any():
        raise ValueError("The selected review area contains no valid backscatter")
    # Keep land out of the background estimate and exclude mask-edge peaks.
    ocean_interior = minimum_filter(valid, size=9, mode="constant") if water_source else valid
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
    mask = ocean_interior & valid & (neighbours >= 0.8 * (31**2 - 9**2)) & (score >= args.threshold) & ((data - mean) >= 5)
    groups, group_count = label(mask, structure=np.ones((3, 3)))
    ids = np.arange(1, group_count + 1)
    areas = np.bincount(groups.ravel(), minlength=group_count + 1)[1:]
    ids = ids[areas >= 2]
    peaks = maximum_position(score, groups, ids.tolist()) if ids.size else []
    ranked = sorted(peaks, key=lambda point: score[point], reverse=True)[:args.max_candidates]

    with open(args.raster, "rb") as file:
        raster_hash = file_digest(file, "sha256").hexdigest()
    low, high = np.nanpercentile(values[valid], [2, 99.7])
    high = max(high, low + 1)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    features = []
    for index, (row, col) in enumerate(ranked, 1):
        top, left = max(0, row - 48), max(0, col - 48)
        crop = values[top:row + 49, left:col + 49]
        preview = np.clip((crop - low) / (high - low) * 255, 0, 255)
        image = f"return-{index:02}.png"
        Image.fromarray(np.nan_to_num(preview).astype("uint8")).save(output / image)
        lon, lat = lonlat(col + 0.5, row + 0.5)
        corners = [lonlat(x, y) for x, y in (
            (left, top), (left + crop.shape[1], top),
            (left + crop.shape[1], top + crop.shape[0]), (left, top + crop.shape[0]),
        )]
        crop_path = f"return-{index:02}.tif"
        gdal.Translate(str(output / crop_path), dataset, srcWin=[left, top, crop.shape[1], crop.shape[0]]).FlushCache()
        candidate_key = f"{scene['product_id']}:{raster_hash}:{row}:{col}"
        features.append({
            "type": "Feature",
            "id": f"sar-return:{sha256(candidate_key.encode()).hexdigest()[:24]}",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "status": "unreviewed_radar_return",
                "identity": None,
                "peak_pixel": {"column": int(col), "row": int(row)},
                "crop_window": {"column": int(left), "row": int(top),
                                "width": crop.shape[1], "height": crop.shape[0]},
                "component_pixels": int(areas[groups[row, col] - 1]),
                "peak_backscatter_db": round(float(values[row, col]), 2),
                "local_contrast_score": round(float(score[row, col]), 2),
                "peak_above_background_db": round(float(data[row, col] - mean[row, col]), 2),
                "preview": image,
                "preview_corners": corners,
                "geotiff": crop_path,
                "nearby_published_case_sources": nearby_case_sources(timeline, scene["acquired_at"], lon, lat),
                "nearby_published_ais_fixes": nearby_ais_fixes(timeline, scene["acquired_at"], lon, lat),
            },
        })
    result = {
        "type": "FeatureCollection",
        "scene": scene,
        "analysis": {"method": "local_backscatter_outlier_v2", "threshold": args.threshold,
                     "minimum_local_contrast_db": 5,
                     "water_mask_applied": bool(water_source),
                     "water_mask_source": Path(water_source).name if water_source else None,
                     "review_status": "needs_human_review" if water_source else "needs_water_mask_and_human_review",
                     "source_review_window_seconds": 3600, "source_review_radius_m": 5000,
                     "input_scale": args.scale, "candidate_limit": args.max_candidates,
                     "preview_stretch_db": [float(low), float(high)],
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
    benchmark = commands.add_parser("benchmark", help="Validate on an RTC scene without creating a case")
    benchmark.set_defaults(case_id=None)
    for command in (detect, benchmark):
        command.add_argument("product")
        command.add_argument("raster")
        command.add_argument("output")
        command.add_argument("--scale", choices=["linear", "db"], required=True)
        masks = command.add_mutually_exclusive_group()
        masks.add_argument("--water-mask", help="Aligned single-band GeoTIFF, with 1 for water")
        masks.add_argument("--land-polygons", help="Land vector file or zipped shapefile to rasterize")
        command.add_argument("--threshold", type=float, default=5)
        command.add_argument("--max-candidates", type=int, default=30)
    args = parser.parse_args()
    if args.command == "scenes":
        print(json.dumps([record for case_id in args.case_id for record in scenes(case_id, case_timeline(case_id))], indent=2))
    else:
        if not 0 < args.threshold < float("inf") or not 1 <= args.max_candidates <= 100:
            parser.error("Use a positive finite threshold and a candidate limit from 1 to 100")
        analyze(args)


if __name__ == "__main__":
    main()

"""Generate a PLAY raster preview from one exact Sentinel-2 acquisition."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote, urlencode, urlparse
from urllib.request import urlopen


def case_scene(incident_id):
    endpoint = "https://play.seacommons.org/api/v1/play/incidents/"
    with urlopen(endpoint + quote(incident_id, safe="") + "/timeline", timeout=20) as response:
        dossier = json.load(response)
    geometry = dossier.get("geometry") or {}
    if geometry.get("type") != "Point" or dossier.get("suppress_inferred_map_evidence"):
        raise ValueError("Case needs an eligible published point to prepare a scene automatically")
    lon, lat = geometry["coordinates"]
    case_time = datetime.fromisoformat(dossier["reported_at"].replace("Z", "+00:00"))
    # A small crop around the published case position, not around an inferred vessel.
    bbox = (lon - 0.025, lat - 0.02, lon + 0.025, lat + 0.02)
    candidates = []
    for item in dossier.get("timeline", []):
        properties = item.get("properties") or {}
        product = properties.get("product_id")
        bounds = properties.get("bbox") or []
        if (item.get("type") != "satellite" or item.get("source") != "copernicus_dataspace"
                or not isinstance(product, str) or not re.match(r"S2[A-Z]_MSIL2A_", product)
                or len(bounds) != 4 or not item.get("at")):
            continue
        if not (bounds[0] <= bbox[0] < bbox[2] <= bounds[2] and bounds[1] <= bbox[1] < bbox[3] <= bounds[3]):
            continue
        at = datetime.fromisoformat(item["at"].replace("Z", "+00:00"))
        if at <= case_time:
            candidates.append((case_time - at, product))
    if not candidates:
        raise ValueError("No archived Sentinel-2 L2A scene spans this crop before the case time")
    return min(candidates)[1], bbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product_id", nargs="?", help="Exact Copernicus product ID shown in PLAY")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"))
    parser.add_argument("--output", type=Path, default=Path("apps/web/public/archive/scenes"))
    parser.add_argument("--case", help="Automatically select a scene for a public PLAY case ID")
    args = parser.parse_args()
    if args.case and not (args.product_id or args.bbox):
        product_id, bbox = case_scene(args.case)
    elif not args.case and args.product_id and args.bbox:
        product_id, bbox = args.product_id, args.bbox
    else:
        parser.error("Provide either --case or a product ID and --bbox")
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -80 <= south < north <= 80
            and east - west <= 0.2 and north - south <= 0.2):
        parser.error("Use a non-crossing bounding box at most 0.2 degrees on each side")
    product = product_id.removesuffix(".SAFE")
    match = re.fullmatch(r"S2[A-Z]_MSIL2A_(\d{4})(\d{2})(\d{2})T\d{6}_[A-Za-z0-9_]+", product)
    if not match:
        parser.error("Expected a Sentinel-2 Level-2A product ID")
    day = "-".join(match.groups())
    query = urlencode({
        "collections": "sentinel-2-l2a",
        "bbox": ",".join(map(str, bbox)),
        "datetime": f"{day}T00:00:00Z/{day}T23:59:59Z",
        "limit": 100,
    })
    with urlopen(f"https://earth-search.aws.element84.com/v1/search?{query}", timeout=20) as response:
        items = json.load(response)["features"]
    item = next((candidate for candidate in items if
                 str(candidate["properties"].get("s2:product_uri", "")).removesuffix(".SAFE") == product), None)
    if item is None:
        raise ValueError("Exact Copernicus product not found for the crop and acquisition day")
    source = next(link["href"] for link in item["links"] if link["rel"] == "self")
    properties = item["properties"]
    if not properties.get("datetime"):
        raise ValueError("Acquisition time missing")
    bounds = item["bbox"]
    if not (bounds[0] <= west < east <= bounds[2] and bounds[1] <= south < north <= bounds[3]):
        raise ValueError("Requested crop is outside the scene bounding box")
    asset = urlparse(item["assets"]["visual"]["href"])
    if asset.scheme != "https" or not (
        asset.hostname == "sentinel-cogs.s3.us-west-2.amazonaws.com"
        or asset.hostname == "sentinel-cogs.s3.amazonaws.com"
    ):
        raise ValueError("Unexpected visual asset host")

    # Output in Web Mercator so the map's raster corners and pixel grid agree.
    def mercator(lon, lat):
        scale = 6378137
        return scale * math.radians(lon), scale * math.asinh(math.tan(math.radians(lat)))

    left, bottom = mercator(west, south)
    right, top = mercator(east, north)
    if args.case:
        args.output /= args.case.encode("utf-8").hex()
    args.output.mkdir(parents=True, exist_ok=True)
    product_slug = product
    image = f"{product_slug}.png"
    with tempfile.TemporaryDirectory(dir=args.output) as directory:
        crop = Path(directory) / "crop.tif"
        preview = Path(directory) / image
        subprocess.run([
            "gdalwarp", "-q", "-t_srs", "EPSG:3857", "-te",
            *map(str, (left, bottom, right, top)), "-ts", "1024", "0",
            "-r", "bilinear", "-dstalpha", "/vsicurl/" + asset.geturl(), str(crop),
        ], check=True, timeout=180)
        subprocess.run(["gdal_translate", "-q", "-of", "PNG", str(crop), str(preview)],
                       check=True, timeout=30)
        manifest = Path(directory) / f"{product_slug}.json"
        manifest.write_text(json.dumps({
            "product_id": product_slug,
            "acquired_at": properties["datetime"],
            "source": source,
            "image": image,
            "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        }, indent=2) + "\n")
        preview.replace(args.output / image)
        manifest.replace(args.output / manifest.name)


if __name__ == "__main__":
    main()

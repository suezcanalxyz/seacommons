#!/usr/bin/env python3
"""Run a fixed manifest of historical Sentinel-1 scenes and create a review queue."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from play_satellite_analysis import analyze
from review_satellite_returns import build_queue, summarize


def run_pilot(manifest_path, land_polygons, output):
    scenes = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Expected a non-empty JSON list of historical radar inputs")
    for scene in scenes:
        if not scene["product"] or scene.get("scale") not in {"db", "linear"}:
            raise ValueError("Each input needs a product and scale (linear or db)")
        if not (manifest_path.parent / scene["raster"]).is_file():
            raise ValueError(f"Raster missing: {scene['raster']}")
    if not land_polygons.is_file():
        raise ValueError("Land polygon file is missing")
    output.mkdir(parents=True, exist_ok=False)
    runs = []
    for index, scene in enumerate(scenes, start=1):
        folder = output / f"scene-{index:03}"
        analyze(SimpleNamespace(
            case_id=scene.get("case_id"), product=scene["product"],
            raster=str(manifest_path.parent / scene["raster"]), output=folder,
            scale=scene["scale"], land_polygons=land_polygons,
            threshold=5, max_candidates=30,
        ))
        runs.append(folder / "radar-returns.geojson")
    queue = output / "review.csv"
    build_queue(runs, queue)
    print(json.dumps({"scenes": len(runs), **summarize(queue)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("land_polygons", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run_pilot(args.manifest, args.land_polygons, args.output)


if __name__ == "__main__":
    main()

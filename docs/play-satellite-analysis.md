# Historical satellite analysis in PLAY

The review pipeline reads the public case timeline and lists its Copernicus Sentinel‑1 GRD products. The detector accepts a georeferenced backscatter raster derived from the chosen product. Its outputs are review candidates and stay local until a reviewer has verified their provenance and interpretation.

## List the source scenes

From the repository root, pass one or more incident IDs:

```sh
python3 scripts/play_satellite_analysis.py scenes 09514982
```

The inventory includes the acquisition time, exact product ID and source record. It sorts scenes by their absolute time difference from the case where the archive provides that value. Coverage and timing alone do not identify a vessel.

## Review a coastal or offshore subset

Use the exact GRD product listed in the inventory. Open it in ESA SNAP, apply the appropriate orbit file, remove thermal noise, calibrate to Sigma0 and terrain correct. Export a single polarisation as a georeferenced GeoTIFF of the marine review area. Retain the pixel values, coordinate reference system and NoData mask. The script takes at most four million pixels. Use a Python 3.11+ environment with GDAL Python bindings, NumPy, SciPy and Pillow.

```sh
python3 scripts/play_satellite_analysis.py detect CASE_ID PRODUCT_ID calibrated-vv.tif review-output --scale linear
```

Use `--scale db` if the export already contains decibels. The output directory must be new. The JSON records the product supplied by the operator and the SHA‑256 of the local input. Verify the raster lineage against the source product before admitting a result as evidence.

For each return, the output contains a point in WGS84, an unmodified georeferenced GeoTIFF crop and a contrast-stretched PNG preview. Open the TIFFs and the GeoJSON in QGIS for review. Nearby published AIS fixes, when available in the same PLAY dossier, appear with their observed times and distances. The local contrast score ranks candidate returns and does not estimate identity or detection probability. Bright clutter, shoreline, structures and wakes can generate false candidates. The workflow leaves identity blank and makes no database writes.

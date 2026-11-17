# Experimental Sentinel-1 SAR chip analysis (not production)

`core.intel.sar_chip_analysis` now reads a **small local single-band linear-amplitude TIFF** and applies a bounded guard-ring CFAR detector. The output contains pixel coordinates of unverified bright scatterers, with `confirmed_vessel=false` and `georeferenced=false`. It does not emit geographic coordinates, vessel identities, case evidence, or alerts. Metadata-only Copernicus STAC search remains a separate discovery step.

The implementation is deliberately limited to 1,048,576 pixels and 64 MiB per TIFF, with input validation, a minimum connected-target size, and a cap of 100 candidates. It runs locally on CPU using NumPy/SciPy/tifffile and has synthetic tests for bright targets, false positives, bad input and TIFF decoding. No cloud paid API is needed.

Before enabling a real satellite case association, the pipeline must obtain a **real Sentinel-1 GRD scene or documented calibrated chip**, record its acquisition time and asset provenance, correctly georeference every candidate, apply land/shore masks and incidence-angle/radiometric calibration, compare against time-aligned AIS and independent GFW detections, and evaluate precision/recall on a labeled maritime benchmark. A bright radar return alone does not prove a vessel, a drone attack, or an incident. Real Copernicus acquisition and detection end-to-end remain unverified.

Install optional dependencies with `pip install '.[sar_chip]'` from `apps/api`. Do not invoke the experimental analyzer from the live worker until the above validation gates are implemented and approved.

# PLAY scene raster preparation

A batch worker can use `build-play-scene.py` with Python 3.9+, GDAL CLI tools and HTTPS access to Earth Search and the Sentinel COG bucket. The worker supplies the Copernicus product ID from the archived scene and a bounded area of interest. The script resolves the exact Earth Search item automatically and projects the colour crop to Web Mercator. No QGIS session is required.

```sh
python scripts/satellite/build-play-scene.py COPERNICUS_PRODUCT \
  --bbox WEST SOUTH EAST NORTH
```

Publish the generated PNG and JSON manifest together under `/archive/scenes/`. PLAY loads the raster automatically when the matching Copernicus scene is selected. The overlay shows acquisition pixels from that product. It carries no ship identification or vessel detection result.

The generator is a batch stage for selected optical scenes. Dispatch and publication still need to be connected to the running ingestion pipeline. Radar imagery and vessel detections are separate inputs.

import React, { useEffect, useRef, useState } from 'react';
import 'cesium/Build/Cesium/Widgets/widgets.css';

const DEFAULT_LAT = 35.52;
const DEFAULT_LON = 14.08;
const MAX_PERSON_CUBES = 24;

function trajectoryFromGeoJson(geojson, fallbackLon, fallbackLat) {
  const feature = geojson?.features?.find((item) => item.geometry?.type === 'LineString');
  const coordinates = feature?.geometry?.coordinates
    ?.filter((point) => Array.isArray(point) && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1])))
    .map((point) => [Number(point[0]), Number(point[1])]);
  const safeCoordinates = coordinates?.length >= 2 ? coordinates : [[fallbackLon, fallbackLat]];
  const rawTimes = feature?.properties?.timestamps_utc || [];
  const parsedTimes = rawTimes.map((value) => Date.parse(value));
  const validTimes = parsedTimes.length === safeCoordinates.length
    && parsedTimes.every(Number.isFinite)
    && parsedTimes.every((value, index) => index === 0 || value > parsedTimes[index - 1]);
  const startTime = validTimes ? parsedTimes[0] : 0;
  const timeOffsets = validTimes
    ? parsedTimes.map((value) => (value - startTime) / 1000)
    : safeCoordinates.map((_, index) => index * 3600);
  const rawSpeeds = feature?.properties?.speed_ms || [];
  const speeds = rawSpeeds.length === safeCoordinates.length
    ? rawSpeeds.map((value) => Math.max(0, Number(value) || 0))
    : safeCoordinates.map(() => 0);
  return { coordinates: safeCoordinates, timeOffsets, speeds };
}

function environmentalState(weather) {
  const height = Math.max(.08, Number(weather?.waves?.significant_height_m) || .65);
  const period = Math.max(2.5, Number(weather?.waves?.period_s) || 5.5);
  const waveDirection = Number(weather?.waves?.direction_deg);
  const windDirection = Number(weather?.wind?.direction_deg);
  const driftDirection = Number(weather?.sar_conditions?.drift_dir_deg);
  const cloudCover = Number(weather?.air?.cloud_cover_pct);
  const visibility = Number(weather?.air?.visibility_km);
  const weatherCode = Number(weather?.air?.weather_code);
  const isDay = weather?.air?.is_day;
  return {
    waveHeight: height,
    wavePeriod: period,
    directionDeg: Number.isFinite(waveDirection)
      ? waveDirection
      : Number.isFinite(windDirection)
        ? windDirection
        : Number.isFinite(driftDirection)
          ? driftDirection
          : 285,
    directionSource: Number.isFinite(waveDirection)
      ? weather?.waves?.direction_source || 'marine model'
      : 'wind proxy',
    windSpeed: Math.max(0, Number(weather?.wind?.speed_ms) || 3.8),
    windGust: Math.max(0, Number(weather?.wind?.gust_speed_ms) || Number(weather?.wind?.speed_ms) || 3.8),
    currentSpeed: Math.max(0, Number(weather?.ocean?.current_speed_ms) || .18),
    currentDirection: Number(weather?.ocean?.current_dir_deg) || 315,
    cloudCover: Number.isFinite(cloudCover) ? Math.min(100, Math.max(0, cloudCover)) : 35,
    visibilityKm: Number.isFinite(visibility) ? Math.max(.2, visibility) : 15,
    precipitationMm: Math.max(0, Number(weather?.air?.precipitation_mm) || 0),
    weatherCode: Number.isFinite(weatherCode) ? weatherCode : 1,
    isDay: typeof isDay === 'boolean' ? isDay : true,
    humidity: Math.min(100, Math.max(0, Number(weather?.air?.humidity_pct) || 65)),
    pressure: Number(weather?.air?.pressure_hpa) || 1013,
    timestamp: weather?.timestamp_utc || new Date().toISOString(),
    source: weather?.source || 'awaiting environmental feed',
  };
}

function weatherDescription(code) {
  if (code === 0) return 'clear';
  if ([1, 2].includes(code)) return 'partly cloudy';
  if (code === 3) return 'overcast';
  if ([45, 48].includes(code)) return 'fog';
  if ([51, 53, 55, 56, 57].includes(code)) return 'drizzle';
  if ([61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return 'rain';
  if ([71, 73, 75, 77, 85, 86].includes(code)) return 'snow';
  if ([95, 96, 99].includes(code)) return 'thunderstorm';
  return 'modelled conditions';
}

export default function PlayCesium({
  active,
  geojson,
  weather,
  lat,
  lon,
  persons,
  onPick,
  selectionEnabled = false,
}) {
  const containerRef = useRef(null);
  const runtimeRef = useRef({
    trajectory: [[DEFAULT_LON, DEFAULT_LAT]],
    trajectoryTimeOffsets: [0],
    trajectorySpeeds: [0],
    environment: environmentalState(null),
    persons: 1,
    startedAt: performance.now(),
    onPick,
    selectionEnabled,
  });
  const sceneRef = useRef(null);
  const [status, setStatus] = useState('loading 3D sea');
  const [error, setError] = useState('');
  const [cameraAltitude, setCameraAltitude] = useState(145);
  const [cameraView, setCameraView] = useState('simulation');
  const [cameraNavSpeed, setCameraNavSpeed] = useState(24);
  const [driftSpeedMs, setDriftSpeedMs] = useState(0);

  useEffect(() => {
    runtimeRef.current.onPick = onPick;
  }, [onPick]);

  useEffect(() => {
    runtimeRef.current.selectionEnabled = selectionEnabled;
  }, [selectionEnabled]);

  useEffect(() => {
    const latitude = Number(lat);
    const longitude = Number(lon);
    const safeLat = Number.isFinite(latitude) ? latitude : DEFAULT_LAT;
    const safeLon = Number.isFinite(longitude) ? longitude : DEFAULT_LON;
    const trajectory = trajectoryFromGeoJson(geojson, safeLon, safeLat);
    runtimeRef.current.trajectory = trajectory.coordinates;
    runtimeRef.current.trajectoryTimeOffsets = trajectory.timeOffsets;
    runtimeRef.current.trajectorySpeeds = trajectory.speeds;
    runtimeRef.current.currentDriftSpeedMs = trajectory.speeds[0] || 0;
    runtimeRef.current.displayDriftSpeedMs = trajectory.speeds[0] || 0;
    setDriftSpeedMs(trajectory.speeds[0] || 0);
    runtimeRef.current.environment = environmentalState(weather);
    runtimeRef.current.persons = Math.max(1, Math.round(Number(persons) || 1));
    runtimeRef.current.startedAt = performance.now();

    const scene = sceneRef.current;
    if (!scene) return;
    scene.refreshScenario();
  }, [geojson, weather, lat, lon, persons]);

  useEffect(() => {
    if (!active || !containerRef.current || sceneRef.current) return undefined;
    let disposed = false;
    let viewer = null;
    let clickHandler = null;
    let removePreRender = null;
    let removeCameraMoveEnd = null;
    let keyHandler = null;
    let keyUpHandler = null;
    let pointerDownHandler = null;
    let pointerUpHandler = null;
    let pointerMoveHandler = null;
    let wheelHandler = null;
    let contextMenuHandler = null;
    let blurHandler = null;

    const start = async () => {
      try {
        const Cesium = await import('cesium');
        if (disposed || !containerRef.current) return;

        const mobileProfile = window.matchMedia(
          '(max-width: 760px), (pointer: coarse)',
        ).matches;
        const waterSegments = mobileProfile ? 72 : 128;
        const cloudCount = mobileProfile ? 10 : 24;
        const waveLineRadius = mobileProfile ? 3 : 5;
        const waveLinePoints = mobileProfile ? 17 : 29;

        Cesium.buildModuleUrl.setBaseUrl('/cesium/');
        viewer = new Cesium.Viewer(containerRef.current, {
          animation: false,
          baseLayer: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          navigationHelpButton: false,
          sceneModePicker: false,
          selectionIndicator: false,
          timeline: false,
          terrainProvider: new Cesium.EllipsoidTerrainProvider(),
          requestRenderMode: false,
          shadows: !mobileProfile,
          targetFrameRate: mobileProfile ? 30 : 60,
        });
        viewer.resolutionScale = mobileProfile ? .72 : 1;

        let globeLayer = null;
        try {
          const naturalEarth = await Cesium.TileMapServiceImageryProvider.fromUrl(
            '/cesium/Assets/Textures/NaturalEarthII',
          );
          globeLayer = viewer.imageryLayers.addImageryProvider(naturalEarth);
          globeLayer.brightness = .72;
          globeLayer.contrast = 1.12;
          globeLayer.saturation = .68;
          globeLayer.gamma = .92;
        } catch {
          // The WGS84 globe remains navigable with its base color.
        }

        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#07121c');
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#071e2a');
        viewer.scene.globe.showGroundAtmosphere = true;
        viewer.scene.globe.depthTestAgainstTerrain = true;
        viewer.scene.globe.enableLighting = true;
        viewer.scene.globe.dynamicAtmosphereLighting = true;
        viewer.scene.globe.dynamicAtmosphereLightingFromSun = true;
        viewer.scene.fog.enabled = true;
        viewer.scene.fog.density = 2.2e-4;
        viewer.scene.skyAtmosphere.show = true;
        viewer.scene.skyBox.show = true;
        viewer.scene.sun.show = true;
        viewer.scene.moon.show = true;
        viewer.scene.atmosphere.dynamicLighting = Cesium.DynamicAtmosphereLightingType.SUNLIGHT;
        viewer.scene.light = new Cesium.SunLight({ intensity: 1.35 });
        viewer.scene.highDynamicRange = !mobileProfile
          && viewer.scene.highDynamicRangeSupported;
        viewer.scene.postProcessStages.fxaa.enabled = true;
        viewer.shadows = !mobileProfile;
        viewer.scene.shadowMap.enabled = !mobileProfile;
        viewer.scene.shadowMap.softShadows = !mobileProfile;
        viewer.scene.shadowMap.darkness = .32;
        viewer.scene.shadowMap.maximumDistance = mobileProfile ? 6_000 : 18_000;
        viewer.scene.globe.maximumScreenSpaceError = mobileProfile ? 3.5 : 1.5;
        viewer.scene.screenSpaceCameraController.minimumZoomDistance = 12;
        viewer.scene.screenSpaceCameraController.maximumZoomDistance = 45_000_000;
        viewer.scene.screenSpaceCameraController.enableCollisionDetection = true;
        viewer.scene.screenSpaceCameraController.zoomEventTypes = [
          Cesium.CameraEventType.WHEEL,
          Cesium.CameraEventType.PINCH,
        ];

        const entities = [];
        const waveLines = [];
        const people = [];
        const clouds = [];
        const runtime = runtimeRef.current;
        const navigation = {
          keys: new Set(),
          looking: false,
          speed: 24,
          lastFrameAt: performance.now(),
        };
        const pose = {
          position: Cesium.Cartesian3.fromDegrees(DEFAULT_LON, DEFAULT_LAT, 3),
          heading: 0,
          altitude: 3,
          longitude: DEFAULT_LON,
          latitude: DEFAULT_LAT,
          timeSeconds: 0,
        };

        const localPoint = (center, east, north, up = 0) => {
          const frame = Cesium.Transforms.eastNorthUpToFixedFrame(center);
          return Cesium.Matrix4.multiplyByPoint(
            frame,
            new Cesium.Cartesian3(east, north, up),
            new Cesium.Cartesian3(),
          );
        };

        // The local sea uses an actual displaced multi-resolution mesh. Geometry
        // is dense around the vessel and progressively coarser at the horizon;
        // the fragment normals add the moving capillary detail between vertices.
        const waterMaterial = new Cesium.Material({
          fabric: {
            type: 'SeaCommonsProceduralSea',
            uniforms: {
              deepColor: Cesium.Color.fromCssColorString('#071f2d'),
              crestColor: Cesium.Color.fromCssColorString('#0a7890'),
              skyColor: Cesium.Color.fromCssColorString('#79b9c9'),
              horizonColor: Cesium.Color.fromCssColorString('#d2e5df'),
              ambientStrength: .045,
              direction: Cesium.Math.toRadians(285),
              frequency: 82,
              speed: .013,
              roughness: .42,
              specularStrength: 1.15,
              foamStrength: .12,
            },
            source: `
              czm_material czm_getMaterial(czm_materialInput materialInput)
              {
                czm_material material = czm_getDefaultMaterial(materialInput);
                vec2 st = materialInput.st;
                vec2 axis = normalize(vec2(sin(direction), cos(direction)));
                vec2 crossAxis = vec2(-axis.y, axis.x);
                float time = czm_frameNumber * speed;
                float primary = sin(dot(st, axis) * frequency + time);
                float secondary = sin(dot(st, crossAxis) * frequency * 0.57 - time * 0.71);
                float detail = sin((st.s + st.t) * frequency * 1.83 + time * 1.31);
                float chop = sin((st.s * 1.71 - st.t * 1.18) * frequency * 2.67 - time * 1.92);
                float wave = primary * 0.48 + secondary * 0.27 + detail * 0.17 + chop * 0.08;
                float crest = smoothstep(0.24, 0.88, wave);
                float undulation = smoothstep(-0.74, 0.72, wave);
                // Finer, faster-varying interference pattern breaks the foam
                // band up into patchy whitecaps instead of one smooth stripe.
                float foamFleck = sin((st.s * 3.7 + st.t * 2.3) * frequency * 4.1 + time * 2.3)
                                 * sin((st.s * 1.3 - st.t * 2.9) * frequency * 3.4 - time * 1.7);
                float foam = smoothstep(0.58, 0.94, wave) * (0.62 + 0.38 * foamFleck) * foamStrength;
                material.diffuse = mix(
                  mix(
                    deepColor.rgb,
                    crestColor.rgb,
                    0.06 + undulation * 0.54 + crest * 0.16
                  ),
                  horizonColor.rgb,
                  foam
                );
                vec3 skyContribution = mix(
                  skyColor.rgb,
                  horizonColor.rgb,
                  0.28 + crest * 0.16
                );
                material.emission = skyContribution * ambientStrength
                  + crestColor.rgb * crest * 0.018;
                material.normal = normalize(vec3(
                  -axis.x * (primary + detail * .34) * roughness
                    - crossAxis.x * (secondary + chop * .22) * roughness * 0.52,
                  -axis.y * (primary + detail * .34) * roughness
                    - crossAxis.y * (secondary + chop * .22) * roughness * 0.52,
                  1.0
                ));
                material.specular = specularStrength;
                material.shininess = 52.0;
                material.alpha = 1.0;
                return material;
              }
            `,
          },
        });
        let waterPrimitive = null;
        // Sea-level datum used by the mesh and by seaHeightAndSlope() below —
        // an arbitrary constant offset (not a real elevation), kept identical
        // in both places so the vessel sits exactly on the rendered surface.
        const BASE_SEA_HEIGHT = 1.25;

        // Shared wave-field sample (superposed sine trains), keyed by absolute
        // east/north meter offsets. Used both by the mesh generator below and
        // by calculatePose()/orientation to place the vessel ON the same
        // surface it is rendered on, instead of an independent decorative
        // sine unrelated to its actual position.
        const waveSample = (worldEast, worldNorth, environment) => {
          const waveHeight = Cesium.Math.clamp(environment.waveHeight, .08, 5);
          const primaryLength = Cesium.Math.clamp(
            1.56 * environment.wavePeriod * environment.wavePeriod,
            22,
            190,
          );
          const secondaryLength = Math.max(13, primaryLength * .46);
          const tertiaryLength = Math.max(8, primaryLength * .23);
          const bearing = Cesium.Math.toRadians(environment.directionDeg);
          const primaryEast = Math.sin(bearing);
          const primaryNorth = Math.cos(bearing);
          const crossEast = Math.cos(bearing);
          const crossNorth = -Math.sin(bearing);
          const k1 = Math.PI * 2 / primaryLength;
          const k2 = Math.PI * 2 / secondaryLength;
          const k3 = Math.PI * 2 / tertiaryLength;
          const amplitude1 = waveHeight * .42;
          const amplitude2 = waveHeight * .17;
          const amplitude3 = Math.min(.18, waveHeight * .07);
          const phase1 = (worldEast * primaryEast + worldNorth * primaryNorth) * k1;
          const phase2 = (worldEast * crossEast + worldNorth * crossNorth) * k2 + 1.7;
          const phase3 = ((worldEast + worldNorth) * .7071) * k3 - .8;
          return {
            sum: amplitude1 * Math.sin(phase1) + amplitude2 * Math.sin(phase2) + amplitude3 * Math.sin(phase3),
            slopeEast: amplitude1 * Math.cos(phase1) * k1 * primaryEast
              + amplitude2 * Math.cos(phase2) * k2 * crossEast
              + amplitude3 * Math.cos(phase3) * k3 * .7071,
            slopeNorth: amplitude1 * Math.cos(phase1) * k1 * primaryNorth
              + amplitude2 * Math.cos(phase2) * k2 * crossNorth
              + amplitude3 * Math.cos(phase3) * k3 * .7071,
          };
        };

        // Sea height + local slope at an arbitrary lon/lat, matching the
        // rendered mesh's fade-out from the current water surface's origin.
        const seaHeightAndSlope = (longitude, latitude) => {
          const environment = runtime.environment;
          const worldEast = longitude * 111_320 * Math.cos(Cesium.Math.toRadians(latitude));
          const worldNorth = latitude * 110_540;
          const wave = waveSample(worldEast, worldNorth, environment);
          let fade = 1;
          if (runtime.waterOriginLon != null && runtime.waterOriginLat != null) {
            const originEast = runtime.waterOriginLon * 111_320
              * Math.cos(Cesium.Math.toRadians(runtime.waterOriginLat));
            const originNorth = runtime.waterOriginLat * 110_540;
            const distance = Math.hypot(worldEast - originEast, worldNorth - originNorth);
            const fadeRatio = Cesium.Math.clamp((distance - 2_300) / 5_600, 0, 1);
            fade = 1 - fadeRatio * fadeRatio * (3 - 2 * fadeRatio);
          }
          return {
            height: BASE_SEA_HEIGHT + fade * wave.sum,
            slopeEast: fade * wave.slopeEast,
            slopeNorth: fade * wave.slopeNorth,
          };
        };

        const makeWaterGeometry = (longitude, latitude) => {
          const environment = runtime.environment;
          const segments = waterSegments;
          const rowSize = segments + 1;
          const halfSize = 13_500;
          const denseRatio = .075;
          const baseHeight = BASE_SEA_HEIGHT;
          const origin = Cesium.Cartesian3.fromDegrees(longitude, latitude, 0);
          const frame = Cesium.Transforms.eastNorthUpToFixedFrame(origin);
          const worldEastOffset = longitude * 111_320 * Math.cos(Cesium.Math.toRadians(latitude));
          const worldNorthOffset = latitude * 110_540;
          const vertexCount = rowSize * rowSize;
          const positions = new Float64Array(vertexCount * 3);
          const normals = new Float32Array(vertexCount * 3);
          const textureCoordinates = new Float32Array(vertexCount * 2);
          const indices = new Uint16Array(segments * segments * 6);

          const remap = (normalized) => {
            const sign = Math.sign(normalized);
            const magnitude = Math.abs(normalized);
            return sign * halfSize * (
              denseRatio * magnitude + (1 - denseRatio) * magnitude * magnitude * magnitude
            );
          };
          let vertexOffset = 0;
          let stOffset = 0;
          for (let row = 0; row <= segments; row += 1) {
            const v = row / segments;
            const north = remap(v * 2 - 1);
            for (let column = 0; column <= segments; column += 1) {
              const u = column / segments;
              const east = remap(u * 2 - 1);
              const worldEast = worldEastOffset + east;
              const worldNorth = worldNorthOffset + north;
              const wave = waveSample(worldEast, worldNorth, environment);
              const distance = Math.hypot(east, north);
              const fadeRatio = Cesium.Math.clamp((distance - 2_300) / 5_600, 0, 1);
              const fade = 1 - fadeRatio * fadeRatio * (3 - 2 * fadeRatio);
              const height = baseHeight + fade * wave.sum;
              // Follow the WGS84 curvature instead of extending a tangent plane
              // to the horizon; this removes the visible edge/dome at sea level.
              const pointLatitude = latitude + north / 110_540;
              const pointLongitude = longitude + east / (
                111_320 * Math.max(.2, Math.cos(Cesium.Math.toRadians(pointLatitude)))
              );
              const point = Cesium.Cartesian3.fromDegrees(
                pointLongitude,
                pointLatitude,
                height,
              );
              positions[vertexOffset] = point.x;
              positions[vertexOffset + 1] = point.y;
              positions[vertexOffset + 2] = point.z;

              const slopeEast = fade * wave.slopeEast;
              const slopeNorth = fade * wave.slopeNorth;
              const worldNormal = Cesium.Matrix4.multiplyByPointAsVector(
                frame,
                new Cesium.Cartesian3(-slopeEast, -slopeNorth, 1),
                new Cesium.Cartesian3(),
              );
              Cesium.Cartesian3.normalize(worldNormal, worldNormal);
              normals[vertexOffset] = worldNormal.x;
              normals[vertexOffset + 1] = worldNormal.y;
              normals[vertexOffset + 2] = worldNormal.z;
              textureCoordinates[stOffset] = u;
              textureCoordinates[stOffset + 1] = v;
              vertexOffset += 3;
              stOffset += 2;
            }
          }

          let indexOffset = 0;
          for (let row = 0; row < segments; row += 1) {
            for (let column = 0; column < segments; column += 1) {
              const lowerLeft = row * rowSize + column;
              const lowerRight = lowerLeft + 1;
              const upperLeft = lowerLeft + rowSize;
              const upperRight = upperLeft + 1;
              indices[indexOffset] = lowerLeft;
              indices[indexOffset + 1] = lowerRight;
              indices[indexOffset + 2] = upperRight;
              indices[indexOffset + 3] = lowerLeft;
              indices[indexOffset + 4] = upperRight;
              indices[indexOffset + 5] = upperLeft;
              indexOffset += 6;
            }
          }

          return new Cesium.Geometry({
            attributes: {
              position: new Cesium.GeometryAttribute({
                componentDatatype: Cesium.ComponentDatatype.DOUBLE,
                componentsPerAttribute: 3,
                values: positions,
              }),
              normal: new Cesium.GeometryAttribute({
                componentDatatype: Cesium.ComponentDatatype.FLOAT,
                componentsPerAttribute: 3,
                values: normals,
              }),
              st: new Cesium.GeometryAttribute({
                componentDatatype: Cesium.ComponentDatatype.FLOAT,
                componentsPerAttribute: 2,
                values: textureCoordinates,
              }),
            },
            indices,
            primitiveType: Cesium.PrimitiveType.TRIANGLES,
            boundingSphere: Cesium.BoundingSphere.fromVertices(positions),
          });
        };
        const replaceWaterSurface = (longitude, latitude) => {
          if (waterPrimitive) viewer.scene.primitives.remove(waterPrimitive);
          runtime.waterOriginLon = longitude;
          runtime.waterOriginLat = latitude;
          const environment = runtime.environment;
          const vertexDirection = Cesium.Math.toRadians(environment.directionDeg).toFixed(8);
          const vertexSpeed = Math.min(
            .038,
            .006 + environment.windSpeed * .0017,
          ).toFixed(8);
          const vertexAmplitude = Math.min(
            1.8,
            Math.max(.06, environment.waveHeight * .34),
          ).toFixed(8);
          const vertexFrequency = Math.min(
            520,
            205 + environment.waveHeight * 36 + environment.windSpeed * 3.5,
          ).toFixed(8);
          waterPrimitive = viewer.scene.primitives.add(new Cesium.Primitive({
            geometryInstances: new Cesium.GeometryInstance({
              geometry: makeWaterGeometry(longitude, latitude),
            }),
            appearance: new Cesium.MaterialAppearance({
              faceForward: true,
              translucent: false,
              closed: false,
              flat: false,
              material: waterMaterial,
              vertexShaderSource: `
                in vec3 position3DHigh;
                in vec3 position3DLow;
                in vec3 normal;
                in vec2 st;
                in float batchId;

                out vec3 v_positionEC;
                out vec3 v_normalEC;
                out vec2 v_st;

                void main()
                {
                  vec4 p = czm_computePosition();
                  float direction = ${vertexDirection};
                  float speed = ${vertexSpeed};
                  float vertexAmplitude = ${vertexAmplitude};
                  float vertexFrequency = ${vertexFrequency};
                  vec2 axis = normalize(vec2(sin(direction), cos(direction)));
                  vec2 crossAxis = vec2(-axis.y, axis.x);
                  float time = czm_frameNumber * speed;
                  float swell = sin(dot(st, axis) * vertexFrequency + time);
                  float crossSwell = sin(
                    dot(st, crossAxis) * vertexFrequency * .48 - time * .67 + 1.4
                  );
                  float displacement = vertexAmplitude * (swell * .72 + crossSwell * .28);
                  p.xyz += normalize(normal) * displacement;

                  v_positionEC = (czm_modelViewRelativeToEye * p).xyz;
                  v_normalEC = czm_normal * normal;
                  v_st = st;
                  gl_Position = czm_modelViewProjectionRelativeToEye * p;
                }
              `,
            }),
            shadows: Cesium.ShadowMode.RECEIVE_ONLY,
            asynchronous: false,
          }));
        };

        const cloudCollection = viewer.scene.primitives.add(new Cesium.CloudCollection({
          noiseDetail: mobileProfile ? 12 : 20,
          noiseOffset: new Cesium.Cartesian3(),
        }));
        for (let index = 0; index < cloudCount; index += 1) {
          clouds.push(cloudCollection.add({
            show: false,
            position: Cesium.Cartesian3.fromDegrees(DEFAULT_LON, DEFAULT_LAT, 900),
            scale: new Cesium.Cartesian2(450, 220),
            maximumSize: new Cesium.Cartesian3(680, 320, 190),
            slice: .42,
            brightness: .85,
          }));
        }

        const updateCloudField = (longitude, latitude) => {
          const environment = runtime.environment;
          const origin = Cesium.Cartesian3.fromDegrees(longitude, latitude, 0);
          const visibleClouds = Math.round(clouds.length * environment.cloudCover / 100);
          clouds.forEach((cloud, index) => {
            const angle = index * 2.39996 + Cesium.Math.toRadians(environment.directionDeg);
            const distance = 1250 + (index % 6) * 620 + Math.floor(index / 6) * 310;
            const altitude = 520 + (index % 5) * 135 + environment.humidity * 2.2;
            cloud.position = localPoint(
              origin,
              Math.sin(angle) * distance,
              Math.cos(angle) * distance,
              altitude,
            );
            const width = 430 + (index % 4) * 145;
            const depth = 185 + (index % 3) * 65;
            cloud.scale = new Cesium.Cartesian2(width, depth);
            cloud.maximumSize = new Cesium.Cartesian3(width * 1.42, depth * 1.45, depth);
            cloud.brightness = environment.isDay
              ? Math.max(.48, 1 - environment.cloudCover / 230)
              : .22;
            cloud.color = environment.cloudCover > 78
              ? Cesium.Color.fromCssColorString('#b2bcc2').withAlpha(.96)
              : Cesium.Color.WHITE.withAlpha(.94);
            cloud.show = index < visibleClouds;
          });
        };

        const applyEnvironment = () => {
          const environment = runtime.environment;
          const cloudRatio = environment.cloudCover / 100;
          const night = environment.isDay === false;
          try {
            viewer.clock.currentTime = Cesium.JulianDate.fromIso8601(environment.timestamp);
          } catch {
            viewer.clock.currentTime = Cesium.JulianDate.now();
          }
          viewer.clock.shouldAnimate = false;
          viewer.scene.light.intensity = night
            ? .18
            : Cesium.Math.lerp(2.05, .72, cloudRatio);
          viewer.scene.light.color = Cesium.Color.fromCssColorString(
            night ? '#9bb8d5' : cloudRatio > .72 ? '#dce4e3' : '#fff2d4',
          );
          // Cesium's astronomical skybox is a star field. During daylight it
          // must be hidden so the atmospheric/background sky remains visible,
          // including on browsers where low-altitude scattering is unavailable.
          viewer.scene.skyBox.show = night;
          viewer.scene.skyAtmosphere.show = true;
          viewer.scene.skyAtmosphere.atmosphereLightIntensity = night
            ? 4
            : Cesium.Math.lerp(56, 28, cloudRatio);
          viewer.scene.skyAtmosphere.atmosphereMieAnisotropy = Cesium.Math.lerp(.88, .72, cloudRatio);
          viewer.scene.skyAtmosphere.hueShift = night ? -.08 : -.025;
          viewer.scene.skyAtmosphere.saturationShift = night ? -.42 : -.08 - cloudRatio * .22;
          viewer.scene.skyAtmosphere.brightnessShift = night ? -.48 : -.05 - cloudRatio * .2;
          viewer.scene.globe.atmosphereLightIntensity = night ? 2.5 : 9.5;
          viewer.scene.fog.density = Math.min(
            .0022,
            Math.max(7e-5, 1 / (environment.visibilityKm * 9500)),
          );
          viewer.scene.backgroundColor = Cesium.Color.fromCssColorString(
            night ? '#020812' : cloudRatio > .72 ? '#728890' : '#82b7c8',
          );

          waterMaterial.uniforms.deepColor = Cesium.Color.fromCssColorString(
            night ? '#020b14' : cloudRatio > .72 ? '#071b25' : '#062737',
          );
          waterMaterial.uniforms.crestColor = Cesium.Color.fromCssColorString(
            night ? '#082539' : cloudRatio > .72 ? '#244b56' : '#0a8196',
          );
          waterMaterial.uniforms.skyColor = Cesium.Color.fromCssColorString(
            night ? '#07172c' : cloudRatio > .72 ? '#71858c' : '#79b9c9',
          );
          waterMaterial.uniforms.horizonColor = Cesium.Color.fromCssColorString(
            night ? '#13283a' : cloudRatio > .72 ? '#aab8b8' : '#d2e5df',
          );
          waterMaterial.uniforms.ambientStrength = night
            ? .018
            : Cesium.Math.lerp(.045, .075, cloudRatio);
          waterMaterial.uniforms.direction = Cesium.Math.toRadians(environment.directionDeg);
          waterMaterial.uniforms.frequency = Math.min(
            560,
            210 + environment.waveHeight * 42 + environment.windSpeed * 4.2,
          );
          waterMaterial.uniforms.speed = Math.min(
            .038,
            .006 + environment.windSpeed * .0017,
          );
          waterMaterial.uniforms.roughness = Math.min(.78, .22 + environment.waveHeight * .13);
          waterMaterial.uniforms.specularStrength = night
            ? .35
            : Math.max(.42, 1.9 - cloudRatio * 1.25);
          waterMaterial.uniforms.foamStrength = Math.min(
            .5,
            Math.max(.04, (environment.waveHeight - .35) * .12 + environment.windSpeed * .008),
          );
        };

        const offsetFromPose = (forward, right, up = 0) => {
          const east = Math.sin(pose.heading) * forward + Math.cos(pose.heading) * right;
          const north = Math.cos(pose.heading) * forward - Math.sin(pose.heading) * right;
          return localPoint(pose.position, east, north, up);
        };

        const calculatePose = () => {
          const path = runtime.trajectory;
          const nowSeconds = (performance.now() - runtime.startedAt) / 1000;
          const offsets = runtime.trajectoryTimeOffsets || [];
          const totalModelSeconds = Math.max(1, offsets[offsets.length - 1] || (path.length - 1) * 3600);
          const journeySeconds = Math.max(36, totalModelSeconds / 400);
          const normalized = (nowSeconds % journeySeconds) / journeySeconds;
          const modelSeconds = normalized * totalModelSeconds;
          let index = Math.max(0, path.length - 2);
          for (let candidate = 0; candidate < path.length - 1; candidate += 1) {
            if (modelSeconds <= (offsets[candidate + 1] ?? (candidate + 1) * 3600)) {
              index = candidate;
              break;
            }
          }
          const intervalStart = offsets[index] ?? index * 3600;
          const intervalEnd = offsets[index + 1] ?? (index + 1) * 3600;
          const fraction = path.length > 1
            ? Cesium.Math.clamp((modelSeconds - intervalStart) / Math.max(1, intervalEnd - intervalStart), 0, 1)
            : 0;
          const first = path[index] || path[0];
          const second = path[index + 1] || first;
          let longitude = first[0];
          let latitude = first[1];
          if (first[0] !== second[0] || first[1] !== second[1]) {
            const geodesic = new Cesium.EllipsoidGeodesic(
              Cesium.Cartographic.fromDegrees(first[0], first[1]),
              Cesium.Cartographic.fromDegrees(second[0], second[1]),
            );
            const interpolated = geodesic.interpolateUsingFraction(fraction);
            longitude = Cesium.Math.toDegrees(interpolated.longitude);
            latitude = Cesium.Math.toDegrees(interpolated.latitude);
          }
          const dx = (second[0] - first[0]) * Math.cos(Cesium.Math.toRadians(latitude));
          const dy = second[1] - first[1];
          const heading = Math.atan2(dx, dy);
          const firstSpeed = runtime.trajectorySpeeds?.[index] || 0;
          const secondSpeed = runtime.trajectorySpeeds?.[index + 1] || firstSpeed;
          runtime.currentDriftSpeedMs = Cesium.Math.lerp(firstSpeed, secondSpeed, fraction);
          // Sample the same wave field the rendered mesh uses at the vessel's
          // actual position, instead of a decorative time-only sine — the
          // hull now visibly rides the real sea surface under it.
          const HULL_FREEBOARD = 4 - BASE_SEA_HEIGHT;
          const surface = seaHeightAndSlope(longitude, latitude);
          const altitude = HULL_FREEBOARD + surface.height;
          pose.position = Cesium.Cartesian3.fromDegrees(longitude, latitude, altitude);
          pose.surfaceSlopeEast = surface.slopeEast;
          pose.surfaceSlopeNorth = surface.slopeNorth;
          pose.heading = Number.isFinite(heading) ? heading : 0;
          pose.altitude = altitude;
          pose.longitude = longitude;
          pose.latitude = latitude;
          pose.timeSeconds = nowSeconds;
          return pose;
        };

        const orientation = new Cesium.CallbackProperty(() => {
          // Roll/pitch derived from the local sea-surface slope under the
          // hull (small-angle approximation: angle ≈ slope), sampled along
          // and across the vessel's heading — replaces the previous
          // decorative sine that was unrelated to the rendered surface.
          const forwardSlope = (pose.surfaceSlopeEast || 0) * Math.sin(pose.heading)
            + (pose.surfaceSlopeNorth || 0) * Math.cos(pose.heading);
          const rightSlope = (pose.surfaceSlopeEast || 0) * Math.cos(pose.heading)
            - (pose.surfaceSlopeNorth || 0) * Math.sin(pose.heading);
          const roll = Cesium.Math.clamp(-rightSlope, -Cesium.Math.toRadians(7), Cesium.Math.toRadians(7));
          const pitch = Cesium.Math.clamp(-forwardSlope, -Cesium.Math.toRadians(4.5), Cesium.Math.toRadians(4.5));
          return Cesium.Transforms.headingPitchRollQuaternion(
            pose.position,
            new Cesium.HeadingPitchRoll(pose.heading, pitch, roll),
          );
        }, false);

        const boatPosition = (forward = 0, right = 0, up = 0) => new Cesium.CallbackProperty(
          () => offsetFromPose(forward, right, up),
          false,
        );

        const hull = viewer.entities.add({
          name: 'Anonymous low-poly vessel',
          position: boatPosition(0, 0, 0),
          orientation,
          viewFrom: new Cesium.Cartesian3(-38, -28, 22),
            box: {
              dimensions: new Cesium.Cartesian3(13, 4.2, 1.8),
              material: Cesium.Color.fromCssColorString('#d9e4df'),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString('#071015'),
              shadows: Cesium.ShadowMode.ENABLED,
            },
        });
        entities.push(hull);

        entities.push(viewer.entities.add({
          position: boatPosition(6.4, 0, .05),
          orientation,
          box: {
            dimensions: new Cesium.Cartesian3(3.2, 2.5, 1.3),
            material: Cesium.Color.fromCssColorString('#b7c7c1'),
            shadows: Cesium.ShadowMode.ENABLED,
          },
        }));
        entities.push(viewer.entities.add({
          position: boatPosition(-2.6, 0, 1.35),
          orientation,
          box: {
            dimensions: new Cesium.Cartesian3(4.3, 3.2, 2.3),
            material: Cesium.Color.fromCssColorString('#304a50'),
            outline: true,
            outlineColor: Cesium.Color.fromCssColorString('#caff3d'),
            shadows: Cesium.ShadowMode.ENABLED,
          },
        }));

        for (let index = 0; index < MAX_PERSON_CUBES; index += 1) {
          const row = Math.floor(index / 4);
          const column = index % 4;
          const cube = viewer.entities.add({
            name: 'Anonymous person unit',
            show: new Cesium.CallbackProperty(() => {
              const represented = Math.min(MAX_PERSON_CUBES, runtime.persons);
              return index < represented;
            }, false),
            position: boatPosition(2.5 - row * 1.15, -1.35 + column * .9, 1.45),
            orientation,
            box: {
              dimensions: new Cesium.Cartesian3(.55, .55, .85),
              material: index % 2
                ? Cesium.Color.fromCssColorString('#ff603c')
                : Cesium.Color.fromCssColorString('#caff3d'),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString('#071015'),
              shadows: Cesium.ShadowMode.ENABLED,
            },
          });
          people.push(cube);
          entities.push(cube);
        }

        const trajectoryEntity = viewer.entities.add({
          name: 'SeaCommons trajectory',
          polyline: {
            positions: new Cesium.CallbackProperty(
              () => Cesium.Cartesian3.fromDegreesArrayHeights(
                runtime.trajectory.flatMap((point) => [point[0], point[1], 7]),
              ),
              false,
            ),
            width: 4,
            arcType: Cesium.ArcType.GEODESIC,
            granularity: Cesium.Math.toRadians(.0025),
            material: new Cesium.PolylineGlowMaterialProperty({
              color: Cesium.Color.fromCssColorString('#ff603c'),
              glowPower: .22,
              taperPower: .8,
            }),
            clampToGround: false,
          },
        });
        entities.push(trajectoryEntity);

        const waveOrigin = Cesium.Cartesian3.fromDegrees(DEFAULT_LON, DEFAULT_LAT, 2);
        for (let index = -waveLineRadius; index <= waveLineRadius; index += 1) {
          const wave = viewer.entities.add({
            name: 'Environmental wave field',
            polyline: {
              positions: new Cesium.CallbackProperty(() => {
                const environment = runtime.environment;
                const bearing = Cesium.Math.toRadians(environment.directionDeg);
                const phaseTravel = ((pose.timeSeconds * Math.max(.45, environment.currentSpeed * 4) + index * 28) % 820) - 410;
                const lateral = index * 27;
                const directionEast = Math.sin(bearing);
                const directionNorth = Math.cos(bearing);
                const crestEast = Math.cos(bearing);
                const crestNorth = -Math.sin(bearing);
                const centerEast = directionEast * phaseTravel + crestEast * lateral;
                const centerNorth = directionNorth * phaseTravel + crestNorth * lateral;
                const center = localPoint(waveOrigin, centerEast, centerNorth, 0);
                const length = 285 + environment.waveHeight * 55;
                return Array.from({ length: waveLinePoints }, (_, pointIndex) => {
                  const across = Cesium.Math.lerp(
                    -length,
                    length,
                    pointIndex / (waveLinePoints - 1),
                  );
                  const ripple = Math.sin(across * .025 + index * .72 + pose.timeSeconds * .7)
                    * (2.2 + environment.waveHeight * 1.8);
                  return localPoint(
                    center,
                    crestEast * across + directionEast * ripple,
                    crestNorth * across + directionNorth * ripple,
                    .28 + environment.waveHeight * .18,
                  );
                });
              }, false),
              width: .85,
              material: new Cesium.ColorMaterialProperty(
                Cesium.Color.fromCssColorString('#bdf7f1').withAlpha(.11),
              ),
            },
          });
          waveLines.push(wave);
          entities.push(wave);
        }

        const refreshScenario = () => {
          const path = runtime.trajectory;
          const first = path[0] || [DEFAULT_LON, DEFAULT_LAT];
          const nextWaveOrigin = Cesium.Cartesian3.fromDegrees(first[0], first[1], 2);
          Cesium.Cartesian3.clone(nextWaveOrigin, waveOrigin);
          replaceWaterSurface(first[0], first[1]);
          if (globeLayer) globeLayer.show = false;
          runtime.lodMode = 'sea';
          applyEnvironment();
          updateCloudField(first[0], first[1]);
          setCameraAltitude(42);
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(first[0], first[1] - .00055, 42),
            orientation: {
              heading: Cesium.Math.toRadians(2),
              pitch: Cesium.Math.toRadians(-31),
              roll: 0,
            },
            duration: 1.1,
            complete: () => setCameraAltitude(Math.max(0, viewer.camera.positionCartographic.height)),
          });
        };

        const setCamera = (mode) => {
          if (mode === 'vessel') {
            setCameraAltitude(24);
            setCameraView('vessel');
            viewer.trackedEntity = hull;
            return;
          }
          viewer.trackedEntity = undefined;
          const first = runtime.trajectory[0] || [DEFAULT_LON, DEFAULT_LAT];
          if (mode === 'overview') {
            const pathPositions = runtime.trajectory.map((point) => (
              Cesium.Cartesian3.fromDegrees(point[0], point[1], 7)
            ));
            const bounds = Cesium.BoundingSphere.fromPoints(pathPositions);
            setCameraView('analysis');
            viewer.camera.flyToBoundingSphere(bounds, {
              offset: new Cesium.HeadingPitchRange(
                0,
                Cesium.Math.toRadians(-89),
                Math.max(2_400, bounds.radius * 2.8),
              ),
              duration: .9,
              complete: () => {
                const altitude = Math.max(0, viewer.camera.positionCartographic.height);
                setCameraAltitude(altitude);
              },
            });
            return;
          }
          const seaView = mode === 'sea';
          setCameraView('simulation');
          setCameraAltitude(seaView ? 42 : 430);
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(
              first[0],
              first[1] - (seaView ? .00055 : .0048),
              seaView ? 42 : 430,
            ),
            orientation: {
              heading: Cesium.Math.toRadians(4),
              pitch: Cesium.Math.toRadians(seaView ? -31 : -32),
              roll: 0,
            },
            duration: .9,
          });
        };

        removePreRender = viewer.scene.preRender.addEventListener(() => {
          calculatePose();
          const nowMs = performance.now();
          const elapsedSeconds = Math.min(.05, Math.max(0, (nowMs - navigation.lastFrameAt) / 1000));
          navigation.lastFrameAt = nowMs;
          if (navigation.looking && navigation.keys.size) {
            const shiftMultiplier = navigation.keys.has('ShiftLeft') || navigation.keys.has('ShiftRight')
              ? 3
              : 1;
            const movement = navigation.speed * shiftMultiplier * elapsedSeconds;
            if (navigation.keys.has('KeyW')) viewer.camera.moveForward(movement);
            if (navigation.keys.has('KeyS')) viewer.camera.moveBackward(movement);
            if (navigation.keys.has('KeyA')) viewer.camera.moveLeft(movement);
            if (navigation.keys.has('KeyD')) viewer.camera.moveRight(movement);
            if (navigation.keys.has('KeyE')) viewer.camera.moveUp(movement);
            if (navigation.keys.has('KeyQ')) viewer.camera.moveDown(movement);
          }
          if (
            nowMs - (runtime.lastSpeedDisplayAt || 0) > 500
            && Math.abs((runtime.currentDriftSpeedMs || 0) - (runtime.displayDriftSpeedMs || 0)) > .002
          ) {
            runtime.lastSpeedDisplayAt = nowMs;
            runtime.displayDriftSpeedMs = runtime.currentDriftSpeedMs || 0;
            setDriftSpeedMs(runtime.displayDriftSpeedMs);
          }
          const cloudDrift = pose.timeSeconds * Math.max(.03, runtime.environment.windSpeed * .018);
          cloudCollection.noiseOffset.x = Math.sin(Cesium.Math.toRadians(runtime.environment.directionDeg)) * cloudDrift;
          cloudCollection.noiseOffset.y = Math.cos(Cesium.Math.toRadians(runtime.environment.directionDeg)) * cloudDrift;
          const altitude = viewer.camera.positionCartographic.height;
          const localSeaMode = altitude < 12_000;
          const lodMode = localSeaMode ? 'sea' : 'globe';
          if (runtime.lodMode !== lodMode) {
            runtime.lodMode = lodMode;
            if (waterPrimitive) waterPrimitive.show = localSeaMode;
            if (globeLayer) globeLayer.show = !localSeaMode;
            waveLines.forEach((entity) => { entity.show = localSeaMode; });
            cloudCollection.show = localSeaMode;
          }
          const altitudeDelta = Math.abs(altitude - (runtime.displayAltitude ?? -1));
          if (altitudeDelta > Math.max(2, altitude * .006)) {
            runtime.displayAltitude = altitude;
            setCameraAltitude(Math.max(0, altitude));
          }
        });
        removeCameraMoveEnd = viewer.camera.moveEnd.addEventListener(() => {
          const altitude = Math.max(0, viewer.camera.positionCartographic.height);
          runtime.displayAltitude = altitude;
          setCameraAltitude(altitude);
          if (!viewer.trackedEntity && !navigation.looking) {
            const altitudeRatio = Cesium.Math.clamp(
              (altitude - 800) / (12_000 - 800),
              0,
              1,
            );
            const transition = altitudeRatio * altitudeRatio * (3 - 2 * altitudeRatio);
            const targetPitch = Cesium.Math.lerp(
              Cesium.Math.toRadians(-31),
              Cesium.Math.toRadians(-89),
              transition,
            );
            if (Math.abs(viewer.camera.pitch - targetPitch) > Cesium.Math.toRadians(.75)) {
              viewer.camera.setView({
                destination: viewer.camera.position,
                orientation: {
                  heading: viewer.camera.heading,
                  pitch: targetPitch,
                  roll: 0,
                },
              });
            }
            setCameraView(altitude >= 8_000 ? 'analysis' : 'simulation');
          }
        });

        keyHandler = (event) => {
          if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
          if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'KeyQ', 'KeyE', 'ShiftLeft', 'ShiftRight'].includes(event.code)) {
            navigation.keys.add(event.code);
            if (navigation.looking) event.preventDefault();
          }
          if (event.code === 'Space') {
            event.preventDefault();
            setCamera('sea');
          } else if (event.key === '1') {
            setCamera('sea');
          } else if (event.key === '2') {
            setCamera('vessel');
          } else if (event.key === '3') {
            setCamera('overview');
          }
        };
        keyUpHandler = (event) => {
          navigation.keys.delete(event.code);
        };
        window.addEventListener('keydown', keyHandler);
        window.addEventListener('keyup', keyUpHandler);

        const canvas = viewer.scene.canvas;
        pointerDownHandler = (event) => {
          if (event.button !== 2) return;
          navigation.looking = true;
          canvas.setPointerCapture?.(event.pointerId);
          event.preventDefault();
        };
        pointerUpHandler = (event) => {
          if (event.button !== 2) return;
          navigation.looking = false;
          canvas.releasePointerCapture?.(event.pointerId);
          event.preventDefault();
        };
        pointerMoveHandler = (event) => {
          if (!navigation.looking || !(event.buttons & 2)) return;
          viewer.trackedEntity = undefined;
          setCameraView('simulation');
          viewer.camera.lookRight(-event.movementX * .0022);
          viewer.camera.lookUp(-event.movementY * .0022);
          event.preventDefault();
        };
        wheelHandler = (event) => {
          if (!navigation.looking) return;
          navigation.speed = Cesium.Math.clamp(
            navigation.speed * (event.deltaY < 0 ? 1.22 : .82),
            .5,
            250_000,
          );
          setCameraNavSpeed(navigation.speed);
          event.preventDefault();
        };
        contextMenuHandler = (event) => event.preventDefault();
        blurHandler = () => {
          navigation.looking = false;
          navigation.keys.clear();
        };
        canvas.addEventListener('pointerdown', pointerDownHandler);
        canvas.addEventListener('pointerup', pointerUpHandler);
        canvas.addEventListener('pointermove', pointerMoveHandler);
        canvas.addEventListener('wheel', wheelHandler, { passive: false });
        canvas.addEventListener('contextmenu', contextMenuHandler);
        window.addEventListener('blur', blurHandler);

        clickHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        clickHandler.setInputAction((movement) => {
          if (!runtime.selectionEnabled) return;
          const cartesian = viewer.camera.pickEllipsoid(movement.position, viewer.scene.globe.ellipsoid);
          if (!cartesian) return;
          const point = Cesium.Cartographic.fromCartesian(cartesian);
          runtime.onPick?.(Cesium.Math.toDegrees(point.latitude), Cesium.Math.toDegrees(point.longitude));
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        sceneRef.current = {
          Cesium,
          viewer,
          refreshScenario,
          setCamera,
          entities,
          waveLines,
          people,
          clouds,
          waterMaterial,
        };
        refreshScenario();
        setStatus('procedural simulation sea');
      } catch (sceneError) {
        console.error('Cesium Play scene failed', sceneError);
        setError('3D sea unavailable; use the 2D operational map.');
        setStatus('3D unavailable');
      }
    };

    start();
    return () => {
      disposed = true;
      removePreRender?.();
      removeCameraMoveEnd?.();
      if (keyHandler) window.removeEventListener('keydown', keyHandler);
      if (keyUpHandler) window.removeEventListener('keyup', keyUpHandler);
      const canvas = viewer?.scene?.canvas;
      if (canvas) {
        if (pointerDownHandler) canvas.removeEventListener('pointerdown', pointerDownHandler);
        if (pointerUpHandler) canvas.removeEventListener('pointerup', pointerUpHandler);
        if (pointerMoveHandler) canvas.removeEventListener('pointermove', pointerMoveHandler);
        if (wheelHandler) canvas.removeEventListener('wheel', wheelHandler);
        if (contextMenuHandler) canvas.removeEventListener('contextmenu', contextMenuHandler);
      }
      if (blurHandler) window.removeEventListener('blur', blurHandler);
      clickHandler?.destroy();
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
      sceneRef.current = null;
    };
  }, [active]);

  const environment = environmentalState(weather);
  const visibleCubes = Math.min(MAX_PERSON_CUBES, Math.max(1, Math.round(Number(persons) || 1)));
  const peoplePerCube = Math.max(1, Math.ceil((Number(persons) || 1) / MAX_PERSON_CUBES));
  const trajectoryFeatures = geojson?.features || [];
  const trajectoryMode = trajectoryFeatures.length === 0
    ? 'awaiting trajectory'
    : trajectoryFeatures.some((feature) => feature.properties?.engine === 'seacommons-browser')
      ? 'live browser engine'
    : trajectoryFeatures.some((feature) => feature.properties?.degraded)
      ? 'degraded estimate'
      : 'OpenDrift result';
  const rainOpacity = Math.min(.62, environment.precipitationMm * .28);

  return (
    <section className={`play-cesium ${active ? 'is-active' : ''} ${cameraAltitude > 600_000 ? 'is-orbital' : ''} ${cameraView === 'analysis' ? 'is-analysis' : ''}`} aria-label="Cesium 3D drift laboratory">
      <div className="play-cesium__viewport" ref={containerRef} />
      <div
        className="play-cesium__weather-fx"
        aria-hidden="true"
        style={{
          '--rain-opacity': rainOpacity,
          '--cloud-shade': environment.cloudCover / 100,
          '--wind-duration': `${Math.max(.38, 1.4 - environment.windSpeed * .08)}s`,
        }}
      />
      <div className="play-cesium__status">
        <span><i className={error ? 'is-error' : ''} /> CESIUM / {status}</span>
        <span>{cameraView === 'vessel' ? 'VESSEL' : cameraView === 'analysis' ? 'ANALYSIS' : 'SIMULATION'} · {cameraAltitude >= 1000 ? `${(cameraAltitude / 1000).toFixed(1)} km` : `${Math.round(cameraAltitude)} m`}</span>
      </div>
      <div className="play-cesium__views" aria-label="Camera views">
        <button type="button" className={cameraView === 'simulation' ? 'is-active' : ''} onClick={() => sceneRef.current?.setCamera('sea')}>1 Simulation</button>
        <button type="button" className={cameraView === 'vessel' ? 'is-active' : ''} onClick={() => sceneRef.current?.setCamera('vessel')}>2 Vessel</button>
        <button type="button" className={cameraView === 'analysis' ? 'is-active' : ''} onClick={() => sceneRef.current?.setCamera('overview')}>3 Analysis</button>
      </div>
      <aside className="play-cesium__instrument">
        <header><span>SEA STATE / NOW</span><span>VISUAL MODEL</span></header>
        <dl>
          <div><dt>Wave</dt><dd>{environment.waveHeight.toFixed(2)} m / {environment.wavePeriod.toFixed(1)} s</dd></div>
          <div><dt>Direction</dt><dd>{Math.round(environment.directionDeg)}° · {environment.directionSource}</dd></div>
          <div><dt>Current</dt><dd>{environment.currentSpeed.toFixed(2)} m/s / {Math.round(environment.currentDirection)}°</dd></div>
          <div><dt>Drift speed</dt><dd>{driftSpeedMs.toFixed(2)} m/s / {(driftSpeedMs * 1.943844).toFixed(2)} kn</dd></div>
          <div><dt>Sky</dt><dd>{Math.round(environment.cloudCover)}% · {weatherDescription(environment.weatherCode)}</dd></div>
          <div><dt>Visibility</dt><dd>{environment.visibilityKm.toFixed(1)} km · {environment.isDay ? 'day' : 'night'}</dd></div>
          <div><dt>People</dt><dd>{visibleCubes} cubes · {peoplePerCube > 1 ? `${peoplePerCube} people/cube` : '1 person/cube'}</dd></div>
        </dl>
        <p>Trajectory: {trajectoryMode}. Geometric swell, dynamic surface normals, sky light and soft sun shadows use current Open-Meteo weather + marine conditions. Vessel translation follows the returned drift trajectory; vertical motion is visual.</p>
      </aside>
      <div className="play-cesium__source">{environment.source}</div>
      <div className="play-cesium__reticle" aria-hidden="true"><i /><i /></div>
      <div className="play-cesium__controls" aria-label="Navigation controls">
        <strong>CESIUM 3D NAV</strong>
        <span><kbd>RMB</kbd> look</span>
        <span><kbd>W A S D</kbd> move</span>
        <span><kbd>Q / E</kbd> down / up</span>
        <span><kbd>SHIFT</kbd> boost</span>
        <span><kbd>WHEEL + RMB</kbd> speed {cameraNavSpeed < 1000 ? `${cameraNavSpeed.toFixed(0)} m/s` : `${(cameraNavSpeed / 1000).toFixed(1)} km/s`}</span>
        <span><kbd>SPACE</kbd> recenter</span>
      </div>
      <div className="play-cesium__hint">Wheel: zoom · zoom in: inclined 3D · zoom out: top-down trajectory analysis</div>
      <div className="play-cesium__touch-hint">1 dito: ruota · 2 dita: zoom/inclina · usa le viste per ricentrare</div>
      {error ? <div className="play-cesium__error">{error}</div> : null}
    </section>
  );
}

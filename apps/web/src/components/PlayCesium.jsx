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
  return coordinates?.length >= 2 ? coordinates : [[fallbackLon, fallbackLat]];
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
    runtimeRef.current.trajectory = trajectoryFromGeoJson(geojson, safeLon, safeLat);
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

    const start = async () => {
      try {
        const Cesium = await import('cesium');
        if (disposed || !containerRef.current) return;

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
        });

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
        viewer.scene.fog.enabled = true;
        viewer.scene.fog.density = 2.2e-4;
        viewer.scene.skyAtmosphere.show = true;
        viewer.scene.skyBox.show = true;
        viewer.scene.sun.show = true;
        viewer.scene.moon.show = true;
        viewer.scene.atmosphere.dynamicLighting = Cesium.DynamicAtmosphereLightingType.SUNLIGHT;
        viewer.scene.light = new Cesium.SunLight({ intensity: 1.35 });
        viewer.scene.postProcessStages.fxaa.enabled = true;
        viewer.scene.screenSpaceCameraController.minimumZoomDistance = 12;
        viewer.scene.screenSpaceCameraController.maximumZoomDistance = 45_000_000;
        viewer.scene.screenSpaceCameraController.enableCollisionDetection = true;

        const entities = [];
        const waveLines = [];
        const people = [];
        const clouds = [];
        const runtime = runtimeRef.current;
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

        // A procedural material keeps the simulation surface deterministic and
        // removes the fragile external normal-map texture. At regional/globe
        // altitude the local patch is intentionally hidden and Cesium takes over.
        const waterMaterial = new Cesium.Material({
          fabric: {
            type: 'SeaCommonsProceduralSea',
            uniforms: {
              deepColor: Cesium.Color.fromCssColorString('#071f2d'),
              crestColor: Cesium.Color.fromCssColorString('#0a7890'),
              direction: Cesium.Math.toRadians(285),
              frequency: 82,
              speed: .013,
              roughness: .42,
              specularStrength: 1.15,
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
                float wave = primary * 0.56 + secondary * 0.29 + detail * 0.15;
                float crest = smoothstep(0.18, 0.92, wave);
                material.diffuse = mix(deepColor.rgb, crestColor.rgb, 0.18 + crest * 0.52);
                material.normal = normalize(vec3(
                  -axis.x * primary * roughness - crossAxis.x * secondary * roughness * 0.45,
                  -axis.y * primary * roughness - crossAxis.y * secondary * roughness * 0.45,
                  1.0
                ));
                material.specular = specularStrength;
                material.shininess = 28.0;
                material.alpha = 1.0;
                return material;
              }
            `,
          },
        });
        let waterPrimitive = null;
        const replaceWaterSurface = (longitude, latitude) => {
          if (waterPrimitive) viewer.scene.primitives.remove(waterPrimitive);
          const longitudeRadius = .12 / Math.max(.25, Math.cos(Cesium.Math.toRadians(latitude)));
          waterPrimitive = viewer.scene.primitives.add(new Cesium.Primitive({
            geometryInstances: new Cesium.GeometryInstance({
              geometry: new Cesium.RectangleGeometry({
                rectangle: Cesium.Rectangle.fromDegrees(
                  longitude - longitudeRadius,
                  latitude - .12,
                  longitude + longitudeRadius,
                  latitude + .12,
                ),
                height: 1.25,
                vertexFormat: Cesium.EllipsoidSurfaceAppearance.VERTEX_FORMAT,
              }),
            }),
            appearance: new Cesium.EllipsoidSurfaceAppearance({
              aboveGround: false,
              faceForward: true,
              translucent: false,
              material: waterMaterial,
            }),
            asynchronous: false,
          }));
        };

        const cloudCollection = viewer.scene.primitives.add(new Cesium.CloudCollection({
          noiseDetail: 20,
          noiseOffset: new Cesium.Cartesian3(),
        }));
        for (let index = 0; index < 24; index += 1) {
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
            night ? '#020812' : cloudRatio > .72 ? '#6c7b82' : '#91bdca',
          );

          waterMaterial.uniforms.deepColor = Cesium.Color.fromCssColorString(
            night ? '#020b14' : cloudRatio > .72 ? '#071b25' : '#062737',
          );
          waterMaterial.uniforms.crestColor = Cesium.Color.fromCssColorString(
            night ? '#082539' : cloudRatio > .72 ? '#244b56' : '#0a8196',
          );
          waterMaterial.uniforms.direction = Cesium.Math.toRadians(environment.directionDeg);
          waterMaterial.uniforms.frequency = Math.min(
            145,
            62 + environment.waveHeight * 12 + environment.windSpeed * 1.6,
          );
          waterMaterial.uniforms.speed = Math.min(
            .038,
            .006 + environment.windSpeed * .0017,
          );
          waterMaterial.uniforms.roughness = Math.min(.78, .22 + environment.waveHeight * .13);
          waterMaterial.uniforms.specularStrength = night
            ? .35
            : Math.max(.42, 1.9 - cloudRatio * 1.25);
        };

        const offsetFromPose = (forward, right, up = 0) => {
          const east = Math.sin(pose.heading) * forward + Math.cos(pose.heading) * right;
          const north = Math.cos(pose.heading) * forward - Math.sin(pose.heading) * right;
          return localPoint(pose.position, east, north, up);
        };

        const calculatePose = () => {
          const path = runtime.trajectory;
          const nowSeconds = (performance.now() - runtime.startedAt) / 1000;
          const journeySeconds = Math.max(36, (path.length - 1) * 9);
          const normalized = (nowSeconds % journeySeconds) / journeySeconds;
          const scaled = normalized * Math.max(1, path.length - 1);
          const index = Math.min(path.length - 2, Math.floor(scaled));
          const fraction = path.length > 1 ? scaled - index : 0;
          const first = path[index] || path[0];
          const second = path[index + 1] || first;
          const longitude = Cesium.Math.lerp(first[0], second[0], fraction);
          const latitude = Cesium.Math.lerp(first[1], second[1], fraction);
          const dx = (second[0] - first[0]) * Math.cos(Cesium.Math.toRadians(latitude));
          const dy = second[1] - first[1];
          const heading = Math.atan2(dx, dy);
          const environment = runtime.environment;
          const primary = Math.sin(nowSeconds * Math.PI * 2 / environment.wavePeriod);
          const secondary = Math.sin(nowSeconds * Math.PI * 2 / (environment.wavePeriod * .57) + 1.2);
          const altitude = 4 + environment.waveHeight * (.34 * primary + .13 * secondary);
          pose.position = Cesium.Cartesian3.fromDegrees(longitude, latitude, altitude);
          pose.heading = Number.isFinite(heading) ? heading : 0;
          pose.altitude = altitude;
          pose.longitude = longitude;
          pose.latitude = latitude;
          pose.timeSeconds = nowSeconds;
          return pose;
        };

        const orientation = new Cesium.CallbackProperty(() => {
          const environment = runtime.environment;
          const roll = Cesium.Math.toRadians(Math.min(7, environment.waveHeight * 2.7))
            * Math.sin(pose.timeSeconds * Math.PI * 2 / (environment.wavePeriod * .73));
          const pitch = Cesium.Math.toRadians(Math.min(4.5, environment.waveHeight * 1.9))
            * Math.sin(pose.timeSeconds * Math.PI * 2 / environment.wavePeriod + .9);
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
          box: {
            dimensions: new Cesium.Cartesian3(13, 4.2, 1.8),
            material: Cesium.Color.fromCssColorString('#d9e4df'),
            outline: true,
            outlineColor: Cesium.Color.fromCssColorString('#071015'),
          },
        });
        entities.push(hull);

        entities.push(viewer.entities.add({
          position: boatPosition(6.4, 0, .05),
          orientation,
          box: {
            dimensions: new Cesium.Cartesian3(3.2, 2.5, 1.3),
            material: Cesium.Color.fromCssColorString('#b7c7c1'),
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
            },
          });
          people.push(cube);
          entities.push(cube);
        }

        const trajectoryEntity = viewer.entities.add({
          name: 'OpenDrift trajectory',
          polyline: {
            positions: new Cesium.CallbackProperty(
              () => Cesium.Cartesian3.fromDegreesArray(runtime.trajectory.flatMap((point) => [point[0], point[1]])),
              false,
            ),
            width: 4,
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
        for (let index = -5; index <= 5; index += 1) {
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
                return Array.from({ length: 29 }, (_, pointIndex) => {
                  const across = Cesium.Math.lerp(-length, length, pointIndex / 28);
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
          setCameraAltitude(145);
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(first[0], first[1] - .0021, 145),
            orientation: {
              heading: Cesium.Math.toRadians(2),
              pitch: Cesium.Math.toRadians(-18),
              roll: 0,
            },
            duration: 1.1,
            complete: () => setCameraAltitude(Math.max(0, viewer.camera.positionCartographic.height)),
          });
        };

        const setCamera = (mode) => {
          if (mode === 'vessel') {
            setCameraAltitude(24);
            viewer.trackedEntity = hull;
            return;
          }
          viewer.trackedEntity = undefined;
          const first = runtime.trajectory[0] || [DEFAULT_LON, DEFAULT_LAT];
          const seaView = mode === 'sea';
          setCameraAltitude(seaView ? 145 : 430);
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(
              first[0],
              first[1] - (seaView ? .0021 : .0048),
              seaView ? 145 : 430,
            ),
            orientation: {
              heading: Cesium.Math.toRadians(4),
              pitch: Cesium.Math.toRadians(seaView ? -18 : -32),
              roll: 0,
            },
            duration: .9,
          });
        };

        removePreRender = viewer.scene.preRender.addEventListener(() => {
          calculatePose();
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
        });

        keyHandler = (event) => {
          if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
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
        window.addEventListener('keydown', keyHandler);

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
    : trajectoryFeatures.some((feature) => feature.properties?.degraded)
      ? 'degraded estimate'
      : 'OpenDrift result';
  const rainOpacity = Math.min(.62, environment.precipitationMm * .28);

  return (
    <section className={`play-cesium ${active ? 'is-active' : ''} ${cameraAltitude > 600_000 ? 'is-orbital' : ''}`} aria-label="Cesium 3D drift laboratory">
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
        <span>{cameraAltitude > 600_000 ? 'ORBIT' : cameraAltitude > 8_000 ? 'REGIONAL' : 'SEA'} · {cameraAltitude >= 1000 ? `${(cameraAltitude / 1000).toFixed(1)} km` : `${Math.round(cameraAltitude)} m`}</span>
      </div>
      <aside className="play-cesium__instrument">
        <header><span>SEA STATE / NOW</span><span>VISUAL MODEL</span></header>
        <dl>
          <div><dt>Wave</dt><dd>{environment.waveHeight.toFixed(2)} m / {environment.wavePeriod.toFixed(1)} s</dd></div>
          <div><dt>Direction</dt><dd>{Math.round(environment.directionDeg)}° · {environment.directionSource}</dd></div>
          <div><dt>Current</dt><dd>{environment.currentSpeed.toFixed(2)} m/s / {Math.round(environment.currentDirection)}°</dd></div>
          <div><dt>Sky</dt><dd>{Math.round(environment.cloudCover)}% · {weatherDescription(environment.weatherCode)}</dd></div>
          <div><dt>Visibility</dt><dd>{environment.visibilityKm.toFixed(1)} km · {environment.isDay ? 'day' : 'night'}</dd></div>
          <div><dt>People</dt><dd>{visibleCubes} cubes · {peoplePerCube > 1 ? `${peoplePerCube} people/cube` : '1 person/cube'}</dd></div>
        </dl>
        <p>Trajectory: {trajectoryMode}. Sky, light and water shader use modelled current conditions from Open-Meteo weather + marine. Vessel translation follows the returned drift trajectory; vertical motion is visual.</p>
      </aside>
      <div className="play-cesium__source">{environment.source}</div>
      <div className="play-cesium__reticle" aria-hidden="true"><i /><i /></div>
      <div className="play-cesium__hint">Drag orbit · wheel altitude · space recenter · double-click origin</div>
      {error ? <div className="play-cesium__error">{error}</div> : null}
    </section>
  );
}

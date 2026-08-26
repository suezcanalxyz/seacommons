import { sampleWaveField } from '../../../features/drift/sceneModel.js';

export const BASE_SEA_HEIGHT = 1.25;

/** Own the displaced procedural sea mesh and its shared height sampler. */
export function createSeaSurface({ Cesium, viewer, runtime, segments }) {
  const material = new Cesium.Material({
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
          float foamFleck = sin((st.s * 3.7 + st.t * 2.3) * frequency * 4.1 + time * 2.3)
                           * sin((st.s * 1.3 - st.t * 2.9) * frequency * 3.4 - time * 1.7);
          float foam = smoothstep(0.58, 0.94, wave) * (0.62 + 0.38 * foamFleck) * foamStrength;
          material.diffuse = mix(
            mix(deepColor.rgb, crestColor.rgb, 0.06 + undulation * 0.54 + crest * 0.16),
            horizonColor.rgb,
            foam
          );
          vec3 skyContribution = mix(skyColor.rgb, horizonColor.rgb, 0.28 + crest * 0.16);
          material.emission = skyContribution * ambientStrength + crestColor.rgb * crest * 0.018;
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
  let primitive = null;
  let originLongitude = null;
  let originLatitude = null;

  function heightAndSlope(longitude, latitude) {
    const environment = runtime.environment;
    const worldEast = longitude * 111_320 * Math.cos(Cesium.Math.toRadians(latitude));
    const worldNorth = latitude * 110_540;
    const wave = sampleWaveField(worldEast, worldNorth, environment);
    let fade = 1;
    if (originLongitude !== null && originLatitude !== null) {
      const originEast = originLongitude * 111_320
        * Math.cos(Cesium.Math.toRadians(originLatitude));
      const originNorth = originLatitude * 110_540;
      const distance = Math.hypot(worldEast - originEast, worldNorth - originNorth);
      const fadeRatio = Cesium.Math.clamp((distance - 2_300) / 5_600, 0, 1);
      fade = 1 - fadeRatio * fadeRatio * (3 - 2 * fadeRatio);
    }
    return {
      height: BASE_SEA_HEIGHT + fade * wave.sum,
      slopeEast: fade * wave.slopeEast,
      slopeNorth: fade * wave.slopeNorth,
    };
  }

  function makeGeometry(longitude, latitude) {
    const environment = runtime.environment;
    const rowSize = segments + 1;
    const halfSize = 13_500;
    const denseRatio = .075;
    const origin = Cesium.Cartesian3.fromDegrees(longitude, latitude, 0);
    const frame = Cesium.Transforms.eastNorthUpToFixedFrame(origin);
    const worldEastOffset = longitude * 111_320 * Math.cos(Cesium.Math.toRadians(latitude));
    const worldNorthOffset = latitude * 110_540;
    const vertexCount = rowSize * rowSize;
    const positions = new Float64Array(vertexCount * 3);
    const normals = new Float32Array(vertexCount * 3);
    const textureCoordinates = new Float32Array(vertexCount * 2);
    const indices = new Uint16Array(segments * segments * 6);

    function remap(normalized) {
      const sign = Math.sign(normalized);
      const magnitude = Math.abs(normalized);
      return sign * halfSize * (
        denseRatio * magnitude + (1 - denseRatio) * magnitude * magnitude * magnitude
      );
    }

    let vertexOffset = 0;
    let textureOffset = 0;
    for (let row = 0; row <= segments; row += 1) {
      const v = row / segments;
      const north = remap(v * 2 - 1);
      for (let column = 0; column <= segments; column += 1) {
        const u = column / segments;
        const east = remap(u * 2 - 1);
        const wave = sampleWaveField(
          worldEastOffset + east,
          worldNorthOffset + north,
          environment,
        );
        const distance = Math.hypot(east, north);
        const fadeRatio = Cesium.Math.clamp((distance - 2_300) / 5_600, 0, 1);
        const fade = 1 - fadeRatio * fadeRatio * (3 - 2 * fadeRatio);
        const height = BASE_SEA_HEIGHT + fade * wave.sum;
        const pointLatitude = latitude + north / 110_540;
        const pointLongitude = longitude + east / (
          111_320 * Math.max(.2, Math.cos(Cesium.Math.toRadians(pointLatitude)))
        );
        const point = Cesium.Cartesian3.fromDegrees(pointLongitude, pointLatitude, height);
        positions[vertexOffset] = point.x;
        positions[vertexOffset + 1] = point.y;
        positions[vertexOffset + 2] = point.z;

        const worldNormal = Cesium.Matrix4.multiplyByPointAsVector(
          frame,
          new Cesium.Cartesian3(-fade * wave.slopeEast, -fade * wave.slopeNorth, 1),
          new Cesium.Cartesian3(),
        );
        Cesium.Cartesian3.normalize(worldNormal, worldNormal);
        normals[vertexOffset] = worldNormal.x;
        normals[vertexOffset + 1] = worldNormal.y;
        normals[vertexOffset + 2] = worldNormal.z;
        textureCoordinates[textureOffset] = u;
        textureCoordinates[textureOffset + 1] = v;
        vertexOffset += 3;
        textureOffset += 2;
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
  }

  function replace(longitude, latitude) {
    if (primitive) viewer.scene.primitives.remove(primitive);
    originLongitude = longitude;
    originLatitude = latitude;
    const environment = runtime.environment;
    const vertexDirection = Cesium.Math.toRadians(environment.directionDeg).toFixed(8);
    const vertexSpeed = Math.min(.038, .006 + environment.windSpeed * .0017).toFixed(8);
    const vertexAmplitude = Math.min(
      1.8,
      Math.max(.06, environment.waveHeight * .34),
    ).toFixed(8);
    const vertexFrequency = Math.min(
      520,
      205 + environment.waveHeight * 36 + environment.windSpeed * 3.5,
    ).toFixed(8);
    primitive = viewer.scene.primitives.add(new Cesium.Primitive({
      geometryInstances: new Cesium.GeometryInstance({ geometry: makeGeometry(longitude, latitude) }),
      appearance: new Cesium.MaterialAppearance({
        faceForward: true,
        translucent: false,
        closed: false,
        flat: false,
        material,
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
  }

  function setVisible(visible) {
    if (primitive) primitive.show = visible;
  }

  return { material, heightAndSlope, replace, setVisible };
}

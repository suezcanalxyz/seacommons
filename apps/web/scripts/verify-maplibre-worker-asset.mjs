import { readdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const distRoot = resolve(import.meta.dirname, '..', 'dist');
const assetsRoot = resolve(distRoot, 'assets');
const assetNames = await readdir(assetsRoot);
const workerNames = assetNames.filter((name) => /^maplibre-gl-worker(?:-[A-Za-z0-9_-]+)?\.mjs$/.test(name));

if (workerNames.length !== 1) {
  throw new Error(`Expected one emitted MapLibre worker asset, found ${workerNames.length}`);
}

const javascriptNames = assetNames.filter((name) => /\.(?:js|mjs)$/.test(name));
const javascript = await Promise.all(
  javascriptNames.map((name) => readFile(resolve(assetsRoot, name), 'utf8')),
);

if (!javascript.some((source) => source.includes(workerNames[0]))) {
  throw new Error(`Built JavaScript does not reference emitted worker ${workerNames[0]}`);
}

console.log(`Verified MapLibre worker asset: assets/${workerNames[0]}`);

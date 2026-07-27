import { copyFileSync, cpSync, existsSync, renameSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const distRoot = resolve(webRoot, 'dist');
const siteRoot = resolve(webRoot, '..', 'site');
const cesiumRoot = resolve(webRoot, 'node_modules', 'cesium', 'Build', 'Cesium');
const consoleIndex = resolve(distRoot, 'index.html');

if (!existsSync(consoleIndex)) {
  throw new Error('Vite console build is missing dist/index.html');
}

renameSync(consoleIndex, resolve(distRoot, 'console.html'));
copyFileSync(resolve(siteRoot, 'index.html'), resolve(distRoot, 'site.html'));
copyFileSync(resolve(siteRoot, 'site.css'), resolve(distRoot, 'site.css'));
copyFileSync(resolve(siteRoot, 'site.js'), resolve(distRoot, 'site.js'));
copyFileSync(resolve(siteRoot, 'suez-theme.css'), resolve(distRoot, 'suez-theme.css'));
for (const directory of ['Assets', 'ThirdParty', 'Widgets', 'Workers']) {
  cpSync(resolve(cesiumRoot, directory), resolve(distRoot, 'cesium', directory), { recursive: true });
}

console.log('Unified package ready: institutional site + Play demo + Live console');

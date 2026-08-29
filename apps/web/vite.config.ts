import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

export default defineConfig(({mode}) => {
  const repoRoot = path.resolve(__dirname, '../..');
  // loadEnv from repo root for local dev; Docker passes vars as real env vars
  const env = { ...loadEnv(mode, repoRoot, ''), ...process.env };
  const publicBase = env.VITE_PUBLIC_BASE || '/';
  return {
    base: publicBase,
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    build: {
      rollupOptions: {
        // Two entry documents from one build: the operational console
        // (index.html -> renamed console.html by package-unified.mjs) and the
        // public institutional site (site.html, served at seacommons.org).
        input: {
          console: path.resolve(__dirname, 'index.html'),
          site: path.resolve(__dirname, 'site.html'),
        },
      },
    },
    server: {
      allowedHosts: ['live.seacommons.org', 'play.seacommons.org'],
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: {
        ignored: ['**/core/data/**', '**/core/**/*.py', '**/*.jsonl'],
      },
    },
  };
});

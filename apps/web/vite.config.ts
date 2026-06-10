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
    server: {
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: {
        ignored: ['**/core/data/**', '**/core/**/*.py', '**/*.jsonl'],
      },
    },
  };
});

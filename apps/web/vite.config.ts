import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

export default defineConfig(({mode}) => {
  const repoRoot = path.resolve(__dirname, '../..');
  // loadEnv from repo root for local dev; Docker passes vars as real env vars
  const env = { ...loadEnv(mode, repoRoot, ''), ...process.env };
  const publicBase = env.VITE_PUBLIC_BASE || '/seacommons/';
  return {
    base: publicBase,
    plugins: [react(), tailwindcss()],
    define: {
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
    },
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

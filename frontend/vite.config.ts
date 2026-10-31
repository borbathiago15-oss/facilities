/// <reference types="vitest/config" />
// As telas novas do Trino Facilities (React). O Flask serve o que sai daqui:
// ``npm run build`` grava em facilities/static/app/, com um manifesto que diz
// ao Flask qual é o arquivo de entrada de hoje (facilities/telas).
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  base: '/static/app/',
  build: {
    outDir: '../facilities/static/app',
    emptyOutDir: true,
    manifest: true,
    rollupOptions: { input: 'src/main.tsx' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/testes.ts'],
  },
});

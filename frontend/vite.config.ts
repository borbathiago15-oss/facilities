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
    rollupOptions: {
      input: 'src/main.tsx',
      // Um pedaço por grupo de telas (App.tsx: campo, passagem, cadastros,
      // rotas, chamados, admin), com o nome do grupo no arquivo.
      output: {
        chunkFileNames: (pedaco) => {
          const m = /src\/(?:paginas\/)?([a-z]+)\/[^/]+$/.exec(pedaco.facadeModuleId || '');
          return `assets/${m ? m[1] : '[name]'}-[hash].js`;
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/testes.ts'],
  },
});

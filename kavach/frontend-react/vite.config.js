import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/run': 'http://127.0.0.1:8000',
      '/audit': 'http://127.0.0.1:8000',
      '/approval': 'http://127.0.0.1:8000',
      '/knowledge': 'http://127.0.0.1:8000',
      '/download': 'http://127.0.0.1:8000',
      '/shield': {
        target: 'http://127.0.0.1:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});

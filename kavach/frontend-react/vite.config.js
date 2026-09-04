import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = process.env.BACKEND_URL || env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';

  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        '/run': backendTarget,
        '/audit': backendTarget,
        '/approval': backendTarget,
        '/knowledge': backendTarget,
        '/download': backendTarget,
        '/auth': backendTarget,
        '/chats': backendTarget,
        '/models': backendTarget,
        '/health': backendTarget,
        '/shield': {
          target: backendTarget,
          ws: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
  };
});

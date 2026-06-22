import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 所有发往后端 bot 的请求都走代理，保持与 :7860 同源，避免 CORS
    proxy: {
      '/api': { target: 'http://localhost:7860', changeOrigin: true },   // ← SmallWebRTC offer/answer
      '/start': { target: 'http://localhost:7860', changeOrigin: true },
      '/sessions': { target: 'http://localhost:7860', changeOrigin: true },
    },
  },
});

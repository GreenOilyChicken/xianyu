import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",  // 后端地址，按需改
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});

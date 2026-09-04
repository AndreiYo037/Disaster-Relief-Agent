import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  publicDir: "public",
  server: {
    port: 5173,
    fs: { allow: [".."] },
    proxy: { "/api": "http://127.0.0.1:8081" },
  },
});

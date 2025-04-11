import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import solidPlugin from "vite-plugin-solid";

export default defineConfig({
  plugins: [solidPlugin(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      "/events": {
        target: "http://localhost:8000/",
        changeOrigin: true,
      },
      "/events_longpoll": {
        target: "http://localhost:8000/",
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "esnext",
  },
});

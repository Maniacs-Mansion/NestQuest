import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { serviceWorkerInjectPlugin } from "./vite-sw-plugin";

export default defineConfig({
  plugins: [react(), serviceWorkerInjectPlugin()],
  test: {
    environment: "jsdom",
  },
});

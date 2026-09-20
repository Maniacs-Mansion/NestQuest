import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "../custom_components/nestquest/www",
    emptyOutDir: false,
    sourcemap: false,
    lib: {
      entry: "src/nestquest-cards.ts",
      formats: ["es"],
      fileName: () => "nestquest-cards.js",
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});

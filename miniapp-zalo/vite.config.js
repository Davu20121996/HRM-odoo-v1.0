import { readFileSync } from "node:fs";
import { defineConfig } from "vite";

export default defineConfig({
    base: "./",
    plugins: [{
        name: "zalo-app-config",
        apply: "build",
        generateBundle() {
            this.emitFile({
                type: "asset",
                fileName: "app-config.json",
                source: readFileSync(new URL("./app-config.json", import.meta.url)),
            });
        },
    }],
    build: {
        outDir: "www",
        modulePreload: { polyfill: false },
        rollupOptions: {
            output: {
                entryFileNames: "assets/[name].module.js",
                chunkFileNames: "assets/[name].[hash].module.js",
                assetFileNames: "assets/[name][extname]",
            },
        },
    },
});

import { copyFile, mkdir } from "node:fs/promises";

const target = "src/dashboard/static/dashboard/vendor";
await mkdir(target, { recursive: true });
await copyFile("node_modules/maplibre-gl/dist/maplibre-gl.mjs", target + "/maplibre-gl.mjs");
await copyFile("node_modules/maplibre-gl/dist/maplibre-gl-shared.mjs", target + "/maplibre-gl-shared.mjs");
await copyFile("node_modules/maplibre-gl/dist/maplibre-gl.css", target + "/maplibre-gl.css");
console.log("Dashboard assets built: MapLibre GL JS 6.2.0");

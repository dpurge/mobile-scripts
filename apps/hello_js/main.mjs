// Example Node app: serves ui/ and reports the Node version at GET /api/info.
import { fileURLToPath } from "node:url";
import { parsePort, runApp } from "../../launcher/scriptkit/node/index.mjs";

const info = () => ({ language: "JavaScript", runtime: process.versions.node });

await runApp({
  uiDir: fileURLToPath(new URL("./ui/", import.meta.url)),
  port: parsePort(process.argv.slice(2)),
  routes: { "GET /api/info": info },
});

// Helpers for Node apps: `--port` parsing and a tiny server (node:* modules only, no npm).
//
// Same contract as the Python helper: accept `--port N`, serve the UI on that port, stop by
// exiting or by `POST /_launcher/stop`. See README.md, "Writing an app".
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HOST = "127.0.0.1";
const FRONTEND_DIR = path.resolve(fileURLToPath(new URL("../../frontend/", import.meta.url)));
const LAUNCHER_PREFIX = "/_launcher/";
const STOP_PATH = "/_launcher/stop";

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
};

/**
 * Return N from `--port N`.
 * @param {string[]} argv arguments without the node and script entries, e.g. process.argv.slice(2)
 * @returns {number}
 * @throws {Error} when the option is missing or not a valid port number.
 */
export function parsePort(argv) {
  const position = argv.indexOf("--port");
  const value = position === -1 ? undefined : argv[position + 1];
  const port = Number(value);
  if (value === undefined || !/^\d+$/.test(value) || port > 65535) {
    throw new Error("Usage: --port N (a number from 0 to 65535)");
  }
  return port;
}

/**
 * Serve `uiDir` at / and the launcher frontend at /_launcher/ until stopped.
 * @param {{uiDir: string, port: number, routes?: Object<string, () => any>}} options `routes`
 *   maps "METHOD /path" (for example "GET /api/info") to a function returning a JSON-able value
 *   (it may return a promise).
 * @returns {Promise<void>} resolves after `POST /_launcher/stop`, so the process then exits with 0.
 */
export function runApp({ uiDir, port, routes = {} }) {
  const uiRoot = path.resolve(uiDir);
  const server = createServer((request, response) => {
    handle(request, response, uiRoot, routes, () => stop(server)).catch((error) => {
      if (response.headersSent) {
        response.end();
      } else {
        sendJson(response, 500, { error: String(error?.message ?? error) });
      }
    });
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.once("close", resolve);
    server.listen(port, HOST);
  });
}

function stop(server) {
  // Closing stops new connections; keep-alive ones would otherwise keep the process alive.
  server.close();
  server.closeAllConnections();
}

async function handle(request, response, uiRoot, routes, requestStop) {
  const pathname = new URL(request.url, `http://${HOST}`).pathname;
  if (request.method === "POST" && pathname === STOP_PATH) {
    sendJson(response, 200, { status: "stopping" });
    response.once("finish", requestStop);
    return;
  }
  const route = routes[`${request.method} ${pathname}`];
  if (route) {
    sendJson(response, 200, await route());
  } else if (request.method === "GET" || request.method === "HEAD") {
    await sendStatic(request, response, pathname, uiRoot);
  } else {
    sendJson(response, 404, { error: "Not found" });
  }
}

async function sendStatic(request, response, pathname, uiRoot) {
  let root = uiRoot;
  let relative = pathname;
  if (pathname.startsWith(LAUNCHER_PREFIX)) {
    root = FRONTEND_DIR;
    relative = pathname.slice(LAUNCHER_PREFIX.length - 1);
  }
  let file;
  try {
    file = path.resolve(root, "." + decodeURIComponent(relative));
  } catch {
    sendJson(response, 400, { error: "Bad request path" });
    return;
  }
  // Resolve first, then check the prefix: this is what stops "..%2f" from leaving the directory.
  if (file !== root && !file.startsWith(root + path.sep)) {
    sendJson(response, 404, { error: "Not found" });
    return;
  }
  try {
    if ((await stat(file)).isDirectory()) {
      file = path.join(file, "index.html");
    }
    const body = await readFile(file);
    response.writeHead(200, {
      "Content-Type": CONTENT_TYPES[path.extname(file).toLowerCase()] ?? "application/octet-stream",
      "Content-Length": body.length,
      "Cache-Control": "no-cache",
    });
    response.end(request.method === "HEAD" ? undefined : body);
  } catch {
    sendJson(response, 404, { error: "Not found" });
  }
}

function sendJson(response, status, body) {
  const payload = JSON.stringify(body);
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
    "Cache-Control": "no-cache",
  });
  response.end(payload);
}

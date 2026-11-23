/** All HTTP calls to the launcher backend live here; components never call fetch directly. */

/**
 * Send a request and return the parsed JSON body.
 * @throws {Error} carrying the server's `error` text (or the status) when the request fails.
 */
async function request(method, url, body) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error ?? `Request failed with status ${response.status}`);
  }
  return payload;
}

/**
 * Fetch the configured apps.
 * @returns {Promise<Array<{name: string, script_path: string}>>}
 */
export async function fetchApps() {
  return (await request("GET", "/api/apps")).apps;
}

/**
 * Replace the whole app list (add, remove, edit and reorder all use this).
 * @param {Array<{name: string, script_path: string}>} apps
 * @returns {Promise<Array<{name: string, script_path: string}>>} the list as saved by the server.
 */
export async function saveApps(apps) {
  return (await request("PUT", "/api/apps", { apps })).apps;
}

/**
 * Start the app at `index`.
 * @param {number} index position in the list
 * @returns {Promise<{name: string, port: number, url: string}>}
 */
export function startApp(index) {
  return request("POST", `/api/apps/${index}/start`);
}

/**
 * Ask the app serving this page to stop (`POST /_launcher/stop`, same origin as the page).
 * @returns {Promise<object>}
 */
export function requestStop() {
  return request("POST", "/_launcher/stop");
}

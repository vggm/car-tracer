export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function getJSON(path) {
  let res;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
  } catch (e) {
    throw new ApiError("network", 0);
  }
  if (!res.ok) throw new ApiError(`HTTP ${res.status}`, res.status);
  try {
    return await res.json();
  } catch (e) {
    throw new ApiError("invalid json", res.status);
  }
}

async function sendJSON(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError("network", 0);
  }
  if (!res.ok) throw new ApiError(`HTTP ${res.status}`, res.status);
  if (res.status === 204) return undefined;
  try {
    return await res.json();
  } catch (e) {
    throw new ApiError("invalid json", res.status);
  }
}

export function postJSON(path, body) {
  return sendJSON("POST", path, body);
}

export async function deleteJSON(path) {
  await sendJSON("DELETE", path);
}

// Una sola petición de avisos en vuelo a la vez (insignia y pantalla Avisos la comparten).
let pendingAlerts = null;
export function getAlerts() {
  if (!pendingAlerts) pendingAlerts = getJSON("/api/panel/alerts").finally(() => { pendingAlerts = null; });
  return pendingAlerts;
}

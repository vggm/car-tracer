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

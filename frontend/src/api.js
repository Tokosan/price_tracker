// Cliente de la API. Cookies de sesión HttpOnly + header CSRF (double submit).

function readCookie(name) {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : "";
}

export class ApiError extends Error {
  constructor(status, detail) {
    const msg =
      typeof detail === "string"
        ? detail
        : detail?.message || (Array.isArray(detail) ? detail.map((d) => d.msg).join(", ") : "Error");
    super(msg);
    this.status = status;
    this.detail = detail;
  }
}

let csrfReady = null;
async function ensureCsrf() {
  if (readCookie("tracker_csrf")) return;
  csrfReady ??= fetch("/api/auth/csrf", { credentials: "same-origin" });
  await csrfReady;
}

// `body` va como JSON; `file` (un Blob/File) va tal cual, con su tipo como Content-Type.
// `keepalive`: la petición sobrevive a cerrar o recargar la página (guardado al salir).
export async function api(path, { method = "GET", body, file, keepalive = false } = {}) {
  const headers = {};
  if (method !== "GET") {
    await ensureCsrf();
    headers["X-CSRF-Token"] = readCookie("tracker_csrf");
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (file !== undefined) headers["Content-Type"] = file.type;
  const resp = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    keepalive,
    body: file !== undefined ? file : body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (resp.status === 204) return null;
  const data = await resp.json().catch(() => null);
  if (!resp.ok) throw new ApiError(resp.status, data?.detail ?? resp.statusText);
  return data;
}

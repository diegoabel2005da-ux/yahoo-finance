export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(r.status, msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.blob()) as Promise<T>;
}

export const api = {
  get: <T = any>(path: string, params?: Record<string, any>) => {
    const q = params
      ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => [k, String(v)]))
      : "";
    return fetch(`/api${path}${q}`, { cache: "no-store" }).then((r) => handle<T>(r));
  },
  post: <T = any>(path: string, body: unknown) =>
    fetch(`/api${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => handle<T>(r)),
  form: <T = any>(path: string, form: FormData) => fetch(`/api${path}`, { method: "POST", body: form }).then((r) => handle<T>(r)),
  download: async (path: string, body: unknown, filename: string) => {
    const r = await fetch(`/api${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const blob = await handle<Blob>(r);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};

/** Respuesta estándar de los endpoints de cálculo. */
export type Calc<T = any> = { result: T; audit_id: number; result_digest: string; engine_version: string };

// Thin fetch wrapper for /api/v1. Errors carry the server's { code, message }.
export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request(method, path, body, isForm = false) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(`/api/v1${path}`, opts);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    if (Array.isArray(d)) throw new ApiError(res.status, 'invalid', d.map((e) => e.msg).join('; '));
    throw new ApiError(res.status, d?.code || 'error', d?.message || 'Something went wrong. Try again.');
  }
  return data;
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
  upload: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return request('POST', '/documents', fd, true);
  },
};

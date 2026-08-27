export function apiUrl(base, path) {
  return `${base.replace(/\/$/, '')}${path}`;
}

export async function fetchJson(base, path, options, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = window.setTimeout(
    () => controller.abort(new DOMException(`Request timeout: ${path}`, 'TimeoutError')),
    timeoutMs,
  );
  try {
    const token = window.__SEACOMMONS_ACCESS_TOKEN__;
    const headers = {
      ...(options?.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    const response = await fetch(apiUrl(base, path), {
      signal: controller.signal,
      ...options,
      headers,
    });
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      const message = text && !text.trimStart().startsWith('<')
        ? text
        : `HTTP ${response.status} — backend unavailable`;
      throw new Error(message);
    }
    const text = await response.text();
    if (!text || text.trimStart().startsWith('<')) {
      throw new Error('Backend returned non-JSON — may still be starting up');
    }
    return JSON.parse(text);
  } finally {
    window.clearTimeout(timer);
  }
}

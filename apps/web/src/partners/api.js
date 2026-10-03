import { resolveSiteApiBase } from '../site/liveApi.js';

export async function workspaceApi(path, token, { method = 'GET', body, signal } = {}) {
  if (!token) throw new Error('Sign in to continue.');
  const response = await fetch(`${resolveSiteApiBase()}/api/v1/workspace${path}`, {
    method, signal, cache: 'no-store',
    headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const message = response.status === 409 ? 'Someone updated this record. Reload it before saving.'
      : response.status === 401 ? 'Your session expired. Sign in again.'
        : response.status === 403 ? 'This account does not have access to this action.'
          : response.status === 503 ? 'Partner access is currently unavailable.' : 'The workspace could not complete this request.';
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

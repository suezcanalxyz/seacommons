import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { UserManager, WebStorageStateStore } from 'oidc-client-ts';

const PUBLIC_HOSTS = new Set(['play.seacommons.org', 'demo.seacommons.org', 'live.seacommons.org']);
const CONTROLLED_HOSTS = new Set(['console.seacommons.org']);
const hostname = window.location.hostname;
const enabled = CONTROLLED_HOSTS.has(hostname)
  || (!PUBLIC_HOSTS.has(hostname) && import.meta.env.VITE_AUTH_ENABLED === 'true');
const AuthContext = createContext({ token: null, user: null });

const manager = enabled ? new UserManager({
  authority: import.meta.env.VITE_OIDC_AUTHORITY || 'https://auth.seacommons.org',
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID || 'seacommons-console',
  redirect_uri: `${window.location.origin}${import.meta.env.BASE_URL}`,
  post_logout_redirect_uri: `${window.location.origin}${import.meta.env.BASE_URL}`,
  response_type: 'code',
  scope: 'openid profile email roles',
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  automaticSilentRenew: true,
}) : null;

export function useAuth() { return useContext(AuthContext); }

export function AuthGate({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(!enabled);
  const [error, setError] = useState('');
  const value = useMemo(() => ({
    user,
    token: user?.access_token || null,
    signOut: () => manager?.signoutRedirect(),
  }), [user]);

  useEffect(() => {
    if (!manager) return undefined;
    let active = true;
    const start = async () => {
      try {
        if (window.location.search.includes('code=') && window.location.search.includes('state=')) {
          await manager.signinRedirectCallback();
          window.history.replaceState({}, document.title, window.location.pathname);
        }
        const current = await manager.getUser();
        if (!active) return;
        if (!current || current.expired) {
          setReady(true);
          return;
        }
        window.__SEACOMMONS_ACCESS_TOKEN__ = current.access_token;
        setUser(current);
        setReady(true);
      } catch (error) {
        console.error('OIDC login failed', error);
        if (active) {
          setError('The identity service did not complete the sign-in request.');
          setReady(true);
        }
      }
    };
    const onLoaded = (next) => {
      window.__SEACOMMONS_ACCESS_TOKEN__ = next.access_token;
      setUser(next);
    };
    manager.events.addUserLoaded(onLoaded);
    start();
    return () => { active = false; manager.events.removeUserLoaded(onLoaded); };
  }, []);

  if (!ready) return <main className="auth-screen auth-screen--loading"><div className="auth-loader" /><p>Establishing a secure session…</p></main>;
  if (enabled && !user) {
    return <main className="auth-screen">
      <section className="auth-card" aria-labelledby="auth-title">
        <a className="auth-wordmark" href="https://seacommons.org">SEA<span>COMMONS</span></a>
        <p className="auth-kicker">Controlled research infrastructure</p>
        <h1 id="auth-title">Operational console</h1>
        <p className="auth-copy">Access is limited to authorised researchers and operational partners. Sessions and material changes are recorded for accountability.</p>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button className="auth-primary" onClick={() => { setError(''); manager.signinRedirect(); }}>Continue with institutional access</button>
        <div className="auth-meta"><span>OIDC / Keycloak</span><span>Research beta</span><span>TLS protected</span></div>
        <p className="auth-help">Access problems? Contact the programme administrator. This console is not a substitute for official emergency services.</p>
      </section>
    </main>;
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

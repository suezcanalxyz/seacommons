import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { createClient } from '@supabase/supabase-js';
import { UserManager, WebStorageStateStore } from 'oidc-client-ts';

const PUBLIC_HOSTS = new Set(['play.seacommons.org', 'demo.seacommons.org', 'live.seacommons.org']);
const CONTROLLED_HOSTS = new Set(['console.seacommons.org', 'engine.seacommons.org', 'futures.seacommons.org']);
const hostname = window.location.hostname;
const localReview = hostname === 'localhost' || hostname === '127.0.0.1';
const futuresSurface = window.location.pathname.endsWith('/futures.html')
  || Boolean(document.getElementById('futures-root'));
const authRequired = (!localReview && futuresSurface)
  || CONTROLLED_HOSTS.has(hostname)
  || (!PUBLIC_HOSTS.has(hostname) && import.meta.env.VITE_AUTH_ENABLED === 'true');

const authority = import.meta.env.VITE_OIDC_AUTHORITY || '';
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || '';
const oidcConfigured = Boolean(authority && clientId);

const authUrl = import.meta.env.VITE_SUEZ_AUTH_URL || '';
const publishableKey = import.meta.env.VITE_SUEZ_AUTH_PUBLISHABLE_KEY || '';
const directConfigured = Boolean(authUrl && publishableKey);

const AuthContext = createContext({ token: null, user: null, signOut: () => undefined });

const manager = authRequired && oidcConfigured ? new UserManager({
  authority,
  client_id: clientId,
  redirect_uri: `${window.location.origin}${import.meta.env.BASE_URL}`,
  post_logout_redirect_uri: `${window.location.origin}${import.meta.env.BASE_URL}`,
  response_type: 'code',
  scope: 'openid profile email roles',
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  automaticSilentRenew: true,
}) : null;

const directClient = authRequired && !oidcConfigured && directConfigured
  ? createClient(authUrl, publishableKey, {
      auth: {
        flowType: 'pkce',
        persistSession: true,
        detectSessionInUrl: true,
      },
    })
  : null;

export function useAuth() { return useContext(AuthContext); }

function DirectAuthGate({ children }) {
  const [session, setSession] = useState(null);
  const [phase, setPhase] = useState('loading');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const loadAccess = useCallback(async (nextSession) => {
    if (!nextSession || !directClient) {
      setSession(null);
      setPhase('signed-out');
      return;
    }

    const { data, error } = await directClient
      .from('systems')
      .select('key')
      .eq('key', 'seacommons')
      .eq('status', 'active')
      .maybeSingle();

    if (error) {
      setMessage(error.message);
      setPhase('error');
      return;
    }

    setSession(nextSession);

    if (!data) {
      setPhase('no-access');
      return;
    }

    window.__SEACOMMONS_ACCESS_TOKEN__ = nextSession.access_token;
    setPhase('authorised');
  }, []);

  useEffect(() => {
    if (!directClient) return undefined;
    let active = true;

    directClient.auth.getSession().then(({ data, error }) => {
      if (!active) return;
      if (error) {
        setMessage(error.message);
        setPhase('error');
        return;
      }
      loadAccess(data.session || null);
    });

    const { data: subscription } = directClient.auth.onAuthStateChange((_event, nextSession) => {
      if (active) loadAccess(nextSession);
    });

    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, [loadAccess]);

  async function sendMagicLink(event) {
    event.preventDefault();
    if (!directClient || !email || busy) return;

    setBusy(true);
    setMessage('');
    const normalized = email.trim().toLowerCase();

    try {
      await fetch(`${authUrl}/functions/v1/futures-auth-request`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          apikey: publishableKey,
        },
        body: JSON.stringify({
          email: normalized,
          continue_path: window.location.pathname + window.location.search,
        }),
      });

      await directClient.auth.signInWithOtp({
        email: normalized,
        options: {
          shouldCreateUser: false,
          emailRedirectTo: window.location.href,
        },
      });
    } catch {
      // Generic response prevents email enumeration.
    }

    setBusy(false);
    setPhase('sent');
  }

  async function signOut() {
    if (!directClient) return;
    await directClient.auth.signOut();
    window.__SEACOMMONS_ACCESS_TOKEN__ = undefined;
    setSession(null);
    setPhase('signed-out');
  }

  const value = useMemo(() => ({
    user: session?.user || null,
    token: session?.access_token || null,
    signOut,
  }), [session]);

  if (phase === 'authorised') {
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
  }

  return <main className="auth-screen">
    <section className="auth-card" aria-labelledby="auth-title">
      <a className="auth-wordmark" href="https://seacommons.org">SEA<span>COMMONS</span></a>
      <p className="auth-kicker">Suez Canal identity</p>

      {phase === 'loading' && <>
        <h1 id="auth-title">Checking access</h1>
        <p className="auth-copy">Validating the shared Suez identity session and SeaCommons grant.</p>
      </>}

      {phase === 'signed-out' && <form className="auth-direct-form" onSubmit={sendMagicLink}>
        <h1 id="auth-title">Access Futures</h1>
        <p className="auth-copy">Use an email already authorised for the SeaCommons partner workspace.</p>
        <label><span>email</span><input type="email" required autoFocus value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <button className="auth-primary" disabled={busy}>{busy ? 'sending…' : 'send magic link'}</button>
      </form>}

      {phase === 'sent' && <>
        <h1 id="auth-title">Check your inbox</h1>
        <p className="auth-copy">If this email is authorised, a single-use sign-in link has been sent.</p>
        <button className="auth-primary" onClick={() => setPhase('signed-out')}>use another email</button>
      </>}

      {phase === 'no-access' && <>
        <h1 id="auth-title">No workspace assigned</h1>
        <p className="auth-copy">Your identity is valid, but this account has no active SeaCommons grant.</p>
        <button className="auth-primary" onClick={signOut}>sign out</button>
      </>}

      {phase === 'error' && <>
        <h1 id="auth-title">Access could not complete</h1>
        <p className="auth-copy">{message || 'The identity service returned an error.'}</p>
        <button className="auth-primary" onClick={() => window.location.reload()}>retry</button>
      </>}

      <div className="auth-meta"><span>Supabase PKCE</span><span>RLS grants</span><span>fail closed</span></div>
      <p className="auth-help">Access problems? Contact the programme administrator.</p>
    </section>
  </main>;
}

function OidcAuthGate({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
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
      } catch (nextError) {
        console.error('OIDC login failed', nextError);
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

    return () => {
      active = false;
      manager.events.removeUserLoaded(onLoaded);
    };
  }, []);

  if (!ready) {
    return <main className="auth-screen auth-screen--loading"><div className="auth-loader" /><p>Establishing a secure session…</p></main>;
  }

  if (!user) {
    return <main className="auth-screen">
      <section className="auth-card" aria-labelledby="auth-title">
        <a className="auth-wordmark" href="https://seacommons.org">SEA<span>COMMONS</span></a>
        <p className="auth-kicker">Suez Canal identity</p>
        <h1 id="auth-title">Access Futures</h1>
        <p className="auth-copy">Continue through the Suez Canal identity layer. Access is assigned to your authorised email.</p>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button className="auth-primary" onClick={() => { setError(''); manager.signinRedirect(); }}>continue via suezcanal.xyz</button>
        <div className="auth-meta"><span>OAuth 2.1 / OIDC</span><span>Suez identity</span><span>TLS protected</span></div>
      </section>
    </main>;
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthGate({ children }) {
  if (!authRequired) {
    return <AuthContext.Provider value={{ token: null, user: null, signOut: () => undefined }}>{children}</AuthContext.Provider>;
  }

  if (oidcConfigured) return <OidcAuthGate>{children}</OidcAuthGate>;
  if (directConfigured) return <DirectAuthGate>{children}</DirectAuthGate>;

  return <main className="auth-screen">
    <section className="auth-card" aria-labelledby="auth-title">
      <a className="auth-wordmark" href="https://suezcanal.xyz">SUEZ<span>CANAL</span></a>
      <p className="auth-kicker">Shared identity</p>
      <h1 id="auth-title">Access is not configured yet</h1>
      <p className="auth-copy">This workspace is closed until the Suez identity provider is connected.</p>
      <div className="auth-meta"><span>fail closed</span><span>no anonymous fallback</span></div>
    </section>
  </main>;
}

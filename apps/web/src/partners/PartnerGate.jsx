import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { createClient } from '@supabase/supabase-js';
import { workspaceApi } from './api.js';

const authUrl = import.meta.env.VITE_PARTNER_SUPABASE_URL;
const authKey = import.meta.env.VITE_PARTNER_SUPABASE_PUBLISHABLE_KEY;
const client = authUrl && authKey ? createClient(authUrl, authKey, {
  auth: { storage: window.sessionStorage, storageKey: 'seacommons-partner-session',
    persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
}) : null;

const Context = createContext(null);
export function usePartner() { return useContext(Context); }

export default function PartnerGate({ children }) {
  const [access, setAccess] = useState(null);
  const [ready, setReady] = useState(!client);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState('email');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [cooldown, setCooldown] = useState(0);
  const requestId = useRef(0);
  const validated = useRef(null);
  const codeInput = useRef(null);

  useEffect(() => {
    if (!client) return undefined;
    let active = true;
    async function validate(session) {
      const id = ++requestId.current;
      if (!session?.access_token) { if (active) { validated.current = null; setAccess(null); setReady(true); } return; }
      if (validated.current?.subject !== session.user?.id) {
        validated.current = null; setAccess(null); setReady(false);
      }
      try {
        const me = await workspaceApi('/me', session.access_token);
        if (active && id === requestId.current) {
          validated.current = me;
          setAccess({ token: session.access_token, ...me }); setError('');
        }
      } catch (err) {
        if (active && id === requestId.current) {
          setAccess(null);
          validated.current = null;
          setError(err.status === 403 ? 'Your account has not been authorised for this workspace.' : err.message);
        }
      } finally { if (active && id === requestId.current) setReady(true); }
    }
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      // Run outside the SDK callback lock.
      queueMicrotask(() => { if (active) validate(session); });
    });
    return () => { active = false; requestId.current += 1; data.subscription.unsubscribe(); };
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = window.setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  useEffect(() => { if (step === 'code') codeInput.current?.focus(); }, [step]);

  async function sendCode(event) {
    event?.preventDefault();
    if (!client || busy || cooldown) return;
    setBusy(true); setError('');
    try {
      const { error: sendError } = await client.auth.signInWithOtp({
        email: email.trim().toLowerCase(), options: { shouldCreateUser: false },
      });
      if (sendError && !['signup_disabled', 'user_not_found'].includes(sendError.code)) {
        throw new Error('We could not request a code. Try again shortly.');
      }
      // Same copy for an unprovisioned account. Never expose the invitation list.
      setStep('code'); setCooldown(60); setCode('');
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  async function verify(event) {
    event.preventDefault();
    if (!client || busy) return;
    setBusy(true); setError('');
    try {
      const { error: verifyError } = await client.auth.verifyOtp({
        email: email.trim().toLowerCase(), token: code.trim(), type: 'email',
      });
      if (verifyError) setError('This code is invalid or expired. Request a new code and try again.');
    } catch { setError('We could not verify the code. Please try again.'); } finally { setBusy(false); }
  }

  async function signOut() {
    requestId.current += 1; validated.current = null; setAccess(null); setStep('email'); setCode(''); setError(''); setReady(true);
    await client?.auth.signOut({ scope: 'local' });
  }

  if (!ready) return <main className="partner-login"><p role="status">Checking your access…</p></main>;
  if (access) return <Context.Provider value={{ ...access, signOut }}>{children}</Context.Provider>;
  return <main className="partner-login">
    <section className="partner-login__form" aria-labelledby="partner-title">
      <a className="partner-brand" href="/site.html">SEA COMMONS</a>
      <h1 id="partner-title">Partner workspace</h1>
      <p>Documents, analysis and project delivery in one shared workspace.</p>
      {error && <p className="partner-error" role="alert">{error}</p>}
      {!client && <p className="partner-notice" role="status">Partner sign-in is being configured. Contact research@seacommons.org for access.</p>}
      {step === 'email' ? <form onSubmit={sendCode}>
        <label htmlFor="partner-email">Work email</label>
        <input id="partner-email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy} />
        <button className="partner-primary" disabled={!client || busy || cooldown > 0}>{busy ? 'Requesting code…' : cooldown ? `Try again in ${cooldown}s` : 'Email me a code'}</button>
        <small>Access is available to authorised email addresses.</small>
      </form> : <form onSubmit={verify}>
        <p className="partner-code-note">If {email} has access, a code will arrive shortly.</p>
        <label htmlFor="partner-code">Email code</label>
        <input ref={codeInput} id="partner-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} disabled={busy} />
        <button className="partner-primary" disabled={busy}>{busy ? 'Checking code…' : 'Continue'}</button>
        <div className="partner-login__links"><button type="button" onClick={sendCode} disabled={busy || cooldown > 0}>{cooldown ? `Resend in ${cooldown}s` : 'Resend code'}</button><button type="button" disabled={busy} onClick={() => { setStep('email'); setCode(''); setError(''); }}>Use another email</button></div>
      </form>}
      <a className="partner-back" href="/site.html">← Back to SeaCommons</a>
    </section>
  </main>;
}

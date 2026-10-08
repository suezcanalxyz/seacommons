# Suez shared identity ↔ SeaCommons Futures rollout

## Authority and boundaries
- Central account UI: https://account.suezcanal.xyz (repository `suezcanalxyz/website`).
- **Real OIDC issuer**: `https://sqnoevmxqwbtovvuzdxf.supabase.co/auth/v1`; validated against live `/.well-known/openid-configuration`.
- SeaCommons relying-party origin: `https://futures.seacommons.org` (repository `suezcanalxyz/seacommons`).
- SeaCommons keeps its own workspace data, project grants, resource authorization and private API. Suez authenticates user identities but does not authorize access to SeaCommons resources.
- All production paths stay fail-closed until a registered OAuth client, approved identities, back-end JWT verification and resource grants are confirmed. Neither `VITE_FUTURES_REVIEW_MODE` nor anonymous mock access may be enabled in production.

## Existing deployment and current blockers (2026-10-08)
- Suez Identity Supabase project `sqnoevmxqwbtovvuzdxf` is ACTIVE_HEALTHY.
- Discovery provides authorization endpoint, token endpoint and JWKS endpoint.
- `account.suezcanal.xyz` is live on Vercel project `website`.
- Its Vercel `VITE_SUEZ_AUTH_URL` and `VITE_SUEZ_AUTH_PUBLISHABLE_KEY` are configured with Suez Identity project public values. Redeployment is required before built Vite assets reflect edits.
- Supabase `auth.oauth_clients`: **0**; `public.access_grants`: **0**. OAuth client registration, tenant grants and verified email invitations have NOT been performed.
- An invitation bootstrap Edge Function `futures-auth-request` exists. Do not mistake existence of the function for an operational authenticated workspace.
- SeaCommons `apps/web/src/auth.jsx` uses PKCE authorization-code flow via `oidc-client-ts`.
- SeaCommons Vercel project must have build-time `VITE_OIDC_AUTHORITY` and `VITE_OIDC_CLIENT_ID` configured only after client registration, and may need an explicit allowed redirect origin.
- Backend issuer/audience/JWKS configuration must match the actual access tokens and authorized SeaCommons API resource; do not switch to a token issuer without a verified server-side contract.

## Required registration (final credentials/administrative setup)
1. In **Suez Identity → Authentication → OAuth Apps**, enable OAuth 2.1 server if not already enabled. Register a public PKCE client `seacommons-futures` with callback URL `https://futures.seacommons.org/`, post-logout URL `https://futures.seacommons.org/`, explicit authorization-code + PKCE, and only appropriate scopes (`openid profile email`). Obtain the actual generated client ID; never invent it or put client secrets in Vite.
2. Set `VITE_OIDC_AUTHORITY=https://sqnoevmxqwbtovvuzdxf.supabase.co/auth/v1` and `VITE_OIDC_CLIENT_ID=<registered-client-id>` in SeaCommons Vercel **production** (plus dedicated previews only with separately allowlisted callbacks).
3. In Suez Vercel set `VITE_SUEZ_FIRST_PARTY_CLIENT_IDS` only to the registered and reviewed client IDs; this suppresses a consent prompt only for trusted first-party clients. Keep `VITE_FUTURES_IDENTITY_READY=false` until partner grants/data access are truly enforced.
4. Configure Suez Auth redirect allowlist and email provider settings; whitelist the precise Account return URL `https://account.suezcanal.xyz/` and OAuth callback URL.
5. Invite explicit user emails in the dedicated identity allowlist; establish per-workspace grants in SeaCommons own back-end, not based merely on a matching email. Do not bootstrap an administrator or auto-grant access to all existing users.
6. Configure SeaCommons API OIDC issuer, JWKS and audience *after inspecting a real issued access token's signed claims*; token signature/issuer/audience/expiry must all validate, then resolve workspace membership separately.
7. Run authorization tests: no invite, expired invite, unknown client, wrong callback, another tenant's project ID, user without grants, bad/expired token, logout and refresh, magic link PKCE return, and successful user in exactly one authorized workspace. Confirm no private data leaks in public Live and Play.
8. Deploy once after validation and verify actual HTTPS flows, network redirects, callback state/nonce, server API 401/403 boundaries, retention and email deliverability. Keep current fail-closed mode until tests pass.

## Security invariants
- Email is a login hint, **not** proof of membership or a project authorization.
- Never place Supabase service-role keys, signing secrets or confidential OAuth client secrets in browser `VITE_*` variables.
- Never mint synthetic OIDC credentials, patch the browser to skip auth, or treat a successful page render as an authenticated workspace.
- No production rollout until real persistence and backend-enforced permissions exist: the current Futures UI contains demonstration data and disabled persistence functions.

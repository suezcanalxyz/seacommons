# Partner workspace

Public project documentation lives at `/docs`. Private collaboration lives at
`/partners.html` (also `/partners` on Vercel). The homepage contains no funding
programme or fundraising CTA. The deck is a workspace document, not a public
frontend document.

## Features

- Overview: recent updates and scheduled deadlines from stored records.
- Documents: text/Markdown references and decks with slide navigation.
- Analysis: internal research notes.
- Workflow: steps, owner, status and due date.
- Milestones: delivery records, owner, status and due date.
- Create/edit for authorised editors; read access for viewers.
- Optimistic versions prevent silent overwrites. Each save creates a private
  revision snapshot. Archiving is an explicit status change.
- Text/Markdown import, maximum 200 KB. Binary attachments and rich file previews
  are not implemented in this release.

All user content stays in `workspace_records` and `workspace_revisions` in the
existing backend database. The browser obtains it only after a signed session
passes server authorisation. Content is never included in the Vite bundle.
Public repository templates are public by definition; do not commit actual
internal notes, partner lists, credentials or confidential source material.

## Email login

Supabase Auth sends a six-digit code. `shouldCreateUser: false` restricts the
flow to provisioned users. Disable public signups and provision only approved
accounts. The server independently checks the signed issuer/audience, token
expiry and a mapping of approved email to exact user subject and organisation.
User-editable metadata and token role claims never determine workspace access.

The workspace uses a separate provider from the existing operational OIDC
system. Partner credentials grant workspace permissions only. Existing
operational endpoints retain their own authorisation.

### Provider configuration

Use a dedicated SeaCommons Supabase Auth project with asymmetric JWT signing
keys (ES256 or RS256). Legacy HS256 keys are deliberately unsupported.

1. Disable new user signups and anonymous sign-in.
2. Provision approved users through the provider's admin UI. Record each user UUID.
3. Configure custom SMTP and a verified sender for partner emails. Supabase's
   default mail service is unsuitable for general partner delivery.
4. Change the Magic Link email template to include `{{ .Token }}` instead of a
   login link. Suggested copy: "Your SeaCommons sign-in code is {{ .Token }}."
5. Set OTP expiry to 600 seconds and retain the provider's request/verification
   rate limits. Use short access token lifetimes. Revocation of email access
   should also remove its server mapping, which the API checks on every request.

Frontend environment (public provider values, never a service-role key):

```text
VITE_PARTNER_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_PARTNER_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
```

Vercel server environment (private API transport):

```text
SEACOMMONS_PARTNER_API_ORIGIN=https://<working-backend-host>
```

The dedicated workspace proxy requires HTTPS and only forwards workspace
resources. It never sends partner tokens or private content through the legacy
HTTP proxy. Without this configuration it fails closed with 503. Local browser
tests call the loopback API directly.

Backend environment:

```text
PARTNER_AUTH_ENABLED=true
PARTNER_AUTH_ISSUER=https://<project-ref>.supabase.co/auth/v1
PARTNER_AUTH_AUDIENCE=authenticated
PARTNER_ACCOUNTS={"approved@example.org":{"subject":"<exact-user-uuid>","organization_id":"seacommons","role":"editor"}}
```

Roles are `viewer`, `editor` and `administrator`. Both editor roles can create
and edit records in their own organisation. There is no cross-organisation
superuser or browser-based invitation management in this release. Keep the
account mapping server-side. Normalise email keys to lowercase.

Sessions persist only in browser session storage and refresh through Supabase.
The workspace renders after `/api/v1/workspace/me` accepts the token. Missing
provider configuration presents an unavailable sign-in state. Backend workspace
routes fail closed even when the operational `AUTH_ENABLED` flag is false.

## API

| Endpoint | Purpose |
| --- | --- |
| GET `/api/v1/workspace/me` | Validate session and current server permissions |
| GET `/api/v1/workspace/records` | Organisation-scoped metadata with pagination |
| GET `/api/v1/workspace/records/{id}` | Full record body |
| POST `/api/v1/workspace/records` | Create, editor only |
| PUT `/api/v1/workspace/records/{id}` | Edit at expected version, editor only |
| GET `/api/v1/workspace/records/{id}/history` | Private revision snapshots |

Responses use `private, no-store`. The API never accepts the organisation from
the client. Foreign record IDs return 404. No anonymous fallback exists.

## Deployment and import

1. Review the PR and run required CI.
2. On the VM, back up the database and apply Alembic migration
   `0032_partner_workspace`. This adds tables only.
3. Configure the dedicated provider and private account mapping. Leave the
   existing production authentication and proxy safeguards enabled.
4. Build the web package and serve `partners.html`. Route `/api/v1/workspace/*`
   to the configured operational backend, not the public demo backend.
5. Test actual code delivery, expiry, unknown email, removed account, viewer
   write denial and organisation separation with provisioned test users.
6. Import the public deck template into the agreed organisation:

```bash
PYTHONPATH=apps/api python -m core.workspace_seed \
  --organization seacommons --deck docs/templates/PROJECT_DECK.md
```

The import is explicit and idempotent by organisation/kind/title. It does not
create partner identities, alter source data or insert invented results.
Editors can then replace the template with real internal content through the UI.

Production activation requires the provider project, SMTP sender, approved
email/user UUID mapping and VM access. No email delivery or production login is
claimed until those checks pass.

Official implementation references:
- https://supabase.com/docs/guides/auth/auth-email-passwordless
- https://supabase.com/docs/guides/auth/jwts
- https://supabase.com/docs/guides/auth/auth-smtp

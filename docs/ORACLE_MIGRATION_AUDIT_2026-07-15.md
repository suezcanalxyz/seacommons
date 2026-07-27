# Oracle and seacommons.org migration audit — 15 July 2026

## Outcome

The production-light SeaCommons stack is deployed on the existing Oracle Always Free VM at
`204.216.210.155`. The previous API was replaced only after a consistent SQLite backup and an
automatic rollback test. The new API, isolated public demo, institutional site, research console,
Dex OIDC provider and Nginx edge are active.

The public DNS cutover and public TLS certificate are the remaining release gates. Until DNS is
changed, `seacommons.suezcanal.xyz` remains the public fallback.

## Recovery and backups

- SSH access was recovered without replacing the production disk.
- Oracle boot-volume backup: `seacommons-pre-migration-2026-07-15`.
- Boot backup OCID:
  `ocid1.bootvolumebackup.oc1.eu-milan-1.abwgsljryq6cs2jiyxw6hbuetzvkme3ghch252cm6ut4kkeqeayeno3p3x6q`.
- Application backup: `/home/ubuntu/seacommons/backups/20260715-pre-v2/`.
- A final cutover database snapshot is stored as `seacommons-final-cutover.db` in that directory.
- SQLite `PRAGMA integrity_check` returned `ok` before the v2 service was enabled.
- The temporary recovery VM and its 50 GB boot volume were terminated after the production
  cutover passed acceptance.

## Deployed topology

| Host | Service | Internal target |
|---|---|---|
| `seacommons.org` | Institutional static site | Nginx static root |
| `www.seacommons.org` | Canonical redirect | `seacommons.org` |
| `console.seacommons.org` | Authenticated live console | Nginx static root |
| `api.seacommons.org` | Operational API | `127.0.0.1:8100` |
| `demo.seacommons.org` | Public isolated demo | Nginx static root |
| `demo-api.seacommons.org` | Demo API and bounded estimate | `127.0.0.1:8101` |
| `auth.seacommons.org` | Dex OIDC | `127.0.0.1:5556` |

The API, demo API and Dex bind only to localhost. The legacy public Uvicorn listener on port 8000
is stopped and its service is disabled. Port 8000 no longer accepts connections and its obsolete
OCI ingress rule has been removed. The public security list now exposes only SSH, HTTP and HTTPS.

## Resource decision

The VM is `VM.Standard.E2.1.Micro` with about 1 GB RAM and 2 GB swap. Attempts to allocate an
Always Free Ampere A1 VM in all Milan fault domains failed because Oracle reported no host capacity.
The current Always Free allowance is also smaller than the original deployment plan.

Consequently, the host runs a stable production-light profile:

- SQLite with consistent backups instead of PostgreSQL/PostGIS;
- host Redis instead of a second cache container;
- Dex with SQLite instead of Keycloak and PostgreSQL;
- inline operational jobs instead of a separate worker;
- no MinIO, Grafana or Prometheus containers;
- a lightweight, explicitly non-operational demo estimate instead of a second OpenDrift engine.

The live console retains the real OpenDrift engine, configured AIS feed, case/audit functions and
optional Telegram/WhatsApp integrations. Moving to PostgreSQL/PostGIS, object storage and separate
workers remains the correct next infrastructure step when A1 capacity is available.

## Acceptance evidence

- API security tests: 12 passed.
- Console TypeScript lint: passed.
- Console production build: passed for both live and demo profiles.
- Nginx configuration test: passed.
- HTTP host routing: all six application hosts return HTTP 200 using host-header tests.
- Operational API health: `runtime_profile=operational`.
- Unauthenticated operational simulation mutation: HTTP 401.
- Demo API health: `runtime_profile=demo`.
- Demo alert completed and returned five GeoJSON features marked `degraded=true` and
  `operational_use=false`.
- Active services: `seacommons-api-v2`, `seacommons-demo-v2`, `seacommons-dex`, `nginx`.
- Legacy `seacommons-api` service: disabled and inactive.

Full browser login and an authenticated live simulation must be rechecked after DNS and HTTPS are
active, because the OIDC issuer is intentionally fixed to `https://auth.seacommons.org`.

## DNS cutover

Set TTL to 300 seconds before the change and create or replace these records:

| Host | Type | Value |
|---|---|---|
| `@` | A | `204.216.210.155` |
| `www` | CNAME | `seacommons.org` |
| `console` | A | `204.216.210.155` |
| `api` | A | `204.216.210.155` |
| `auth` | A | `204.216.210.155` |
| `demo` | A | `204.216.210.155` |
| `demo-api` | A | `204.216.210.155` |

Do not change MX records, `mx.seacommons.org`, SPF, DKIM or other mail records. If a restrictive
CAA record exists, allow Let's Encrypt. After propagation, request certificates for all seven web
names, enable HTTP-to-HTTPS redirects and run the final OIDC/login/simulation acceptance test.

## Follow-up — 27 July 2026

The public cutover is still pending:

- `seacommons.org` resolves to the Aruba placeholder `62.149.128.40`;
- `www.seacommons.org` is a CNAME to `seacommons.org`;
- `console`, `api`, `auth`, `demo` and `demo-api` do not yet exist;
- `seacommons.suezcanal.xyz` remains a Vercel CNAME;
- MX remains `mx.seacommons.org` and must not be changed.

Direct host-header probes against `204.216.210.155` confirm that the institutional site, console,
demo, operational API, demo API and Dex are still responding. The two API health endpoints report
the expected `operational` and `demo` runtime profiles, and Dex publishes issuer
`https://auth.seacommons.org`.

The local SSH known-host fingerprint saved on 15 July is
`SHA256:+ieAWMk/A82h8LyMGEN5MNKsRSv25GqwZhziWln1xD8`. On 27 July the host presented
`SHA256:IbSCdViWO14I2/LDex+8dlk8zdilnFFiU4GuYvUO6mM`. Do not replace the saved key until the new
fingerprint is independently verified through the Oracle Console or serial console. The local OCI
security-token session has expired and cannot currently provide that verification.

Repository defaults, metadata, CORS, frontend API discovery, WebSocket routing and production
reverse-proxy manifests now use the `seacommons.org` topology. Both Caddy and the lightweight Nginx
configuration include a permanent redirect from the legacy hostname to `https://seacommons.org`.
The complete Python test suite, frontend TypeScript check and frontend production build pass.

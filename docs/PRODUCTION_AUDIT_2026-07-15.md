# SeaCommons production audit — 15 July 2026

## Executive result

The repository is substantially closer to a production pilot on `seacommons.org`, but it is not yet certified for unattended production. Authentication, authorization, durable ingestion, case management, object storage, background jobs, observability, governance primitives and the production reverse-proxy stack are implemented. The remaining release gates are an end-to-end deployment rehearsal, backup/restore evidence, load testing and provider-level verification of the messaging channels.

## Verification completed

- API regression suite: **12 passed**.
- Frontend TypeScript check: **passed**.
- Frontend production build: **passed**.
- npm application dependency audit: **0 known vulnerabilities**.
- Python application requirements audit: **0 known vulnerabilities**.
- Bandit scan: **0 high**, 29 medium, 91 low findings across 12,586 lines.
- Hardcoded PostgreSQL pilot passwords removed; startup now requires an environment secret.
- Non-security deduplication identifiers migrated from MD5/SHA-1 to BLAKE2s.
- No visual sidebar remains: operational areas open as a full-screen workspace from a shared navigation bar, and the map is the default view on every viewport.

## Security interpretation

The 29 medium Bandit findings are all B310 warnings around `urllib.request.urlopen`. Most targets are fixed upstream HTTP(S) data services. They are not proof of an exploit, but configurable sources must receive a centralized `http/https` scheme allowlist, DNS/private-network policy, response-size ceiling and timeout before multi-tenant production use. The SHA-1 operation retained for Twilio validation is required by the provider's signature protocol and is used as HMAC, not as a password hash.

The audit of the workstation-wide Python installation reports unrelated vulnerable packages. It is not representative of the API image. The authoritative project audit is the scan of `apps/api/requirements-api.txt`, which currently reports no known vulnerabilities. Production must continue to use an isolated, pinned container environment.

## Production readiness by area

| Area | State | Remaining release gate |
|---|---|---|
| Identity and RBAC | Implemented | Configure and test the real Keycloak realm, MFA and recovery |
| Organizations and case access | Implemented foundation | Add admin UI and explicit cross-organization grant tests |
| Case retention and deletion requests | Implemented foundation | Add approval workflow, object deletion worker and legal-hold evidence |
| Telegram and Twilio/WhatsApp | Signed inbound and Telegram outbound implemented | Pair real provider accounts and complete delivery/retry acceptance tests |
| Database and migrations | PostgreSQL/PostGIS plus Alembic migrations | Rehearse upgrade and point-in-time restore |
| Cache and queue | Valkey plus durable database jobs | Load-test leases, retry storms and worker failover |
| Attachments | S3-compatible MinIO | Validate malware scanning, quotas, lifecycle and restore |
| Metrics and dashboards | Prometheus and Grafana provisioned | Add alert routing and an on-call runbook rehearsal |
| Edge and TLS | Caddy production configuration | Validate DNS, certificates, headers and external probes on `seacommons.org` |
| Frontend | Build passes; sidebar-free workspace | Split the 1.05 MB MapLibre chunk and run accessibility/browser tests |

## Recommended next implementation order

1. Central safe outbound HTTP client with SSRF controls, bounded downloads, retries and circuit breaking.
2. Governance console for organizations, memberships, access grants, retention, deletion approvals and legal holds.
3. End-to-end WhatsApp/Telegram pairing status, encrypted credential storage, delivery receipts and dead-letter operations.
4. ClamAV attachment scanning, MinIO lifecycle policies and verified backup/restore automation.
5. CI gates for tests, migrations, dependency audits, Bandit, container scanning, SBOM and signed releases.
6. Staging deployment on the final topology, followed by load, disaster-recovery and security acceptance tests.

## Open and free stack

The production design remains based on open-source components: Caddy, Keycloak, PostgreSQL/PostGIS, Valkey, MinIO, Prometheus and Grafana. WhatsApp itself is not an open network and production messaging may incur Meta/provider charges; Telegram bot integration is free within Telegram's platform limits. A fully open channel can additionally be provided through Matrix/Element.

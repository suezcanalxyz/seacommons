# Outbound HTTP / SSRF Hardening v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce one enforceable outbound HTTP/HTTPS trust boundary, close SeaCommons' dynamic SSRF paths, and migrate the required configurable call sites without changing collector/domain semantics.

**Architecture:** `core.net.outbound` is the canonical public facade. Pure URL/DNS policy lives in `core/net/policy.py`; pinned sync/async HTTP execution and manual redirects live in `core/net/transport.py`. Call sites choose one code-defined trust profile (`PUBLIC_UNTRUSTED`, `PUBLIC_FIXED`, `OPERATOR_INTERNAL`) and one bounded response contract; request/feed input can never weaken the profile.

**Tech Stack:** Python 3.12, `httpx 0.28.x`, `httpcore 1.0.x`, stdlib `socket/ipaddress/urllib.parse`, PyJWT, Prometheus client, pytest/monkeypatch.

**Spec:** `docs/superpowers/specs/2026-09-09-outbound-http-ssrf-hardening-v1-design.md`

## Global Constraints

- No database/schema, frontend, AIS/radio WebSocket, publication, lifecycle, or collector-classification changes.
- `PUBLIC_UNTRUSTED`: HTTPS/443 only, GET/HEAD only, no userinfo, public-routable DNS answers only, `trust_env=False`.
- `PUBLIC_FIXED`: code-owned HTTPS origins, explicit allowlist, public-routable DNS answers, manual redirects inside allowlist only.
- `OPERATOR_INTERNAL`: exact trusted configured origin may be HTTP/HTTPS, private/loopback/non-standard port; request/feed input cannot choose its origin.
- Redirects: automatic library redirects disabled; maximum three GET/HEAD hops; POST redirects fail closed in v1.
- Response contracts: `IMAGE=8 MiB`, `JSON_TEXT=16 MiB`, `BINARY=32 MiB`; 32 MiB is the absolute v1 ceiling.
- Every timeout component is finite and at most 120 s; existing 90 s drift-worker behavior remains valid.
- Errors/logs/metrics never include query strings, credentials, authorization values, response bodies, IPs, or unbounded host labels.
- Blocked requests never retry through a legacy direct HTTP client.
- Required v1 call sites: image extraction, X/Twitter media, auto-drift, remote drift worker, OIDC/JWKS, forensic witness endpoints.

---

### Task 1: Pure outbound policy, URL normalization, and DNS/IP classification

**Files:**
- Create: `apps/api/core/net/__init__.py`
- Create: `apps/api/core/net/policy.py`
- Create: `tests/test_outbound_policy.py`

**Interfaces:**
- Produces `TrustProfile(StrEnum)`, `ResponseContract`, `OutboundError(code: str)`, `NormalizedOrigin`, `ValidatedTarget`, `normalize_origin()`, `resolve_target()`, and constants `IMAGE`, `JSON_TEXT`, `BINARY`.
- `resolve_target()` accepts an injected resolver in tests and returns only already-validated IP addresses; it performs no network I/O beyond DNS resolution.

- [ ] **Step 1: Write RED tests for profile-independent normalization and forbidden targets**

```python
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/a", "https://10.1.2.3/a", "https://[::1]/a",
    "https://169.254.169.254/latest/meta-data", "https://user:pw@example.com/a",
    "ftp://example.com/a", "https://example.com:8443/a",
])
def test_public_untrusted_rejects_forbidden_destination_shapes(url):
    with pytest.raises(OutboundError) as exc:
        resolve_target(url, profile=TrustProfile.PUBLIC_UNTRUSTED, resolver=fake_resolver)
    assert exc.value.code in {"blocked_target", "invalid_scheme", "invalid_port"}
```

Also cover RFC1918, link-local, multicast, unspecified, reserved, IPv4-mapped IPv6, terminal-dot hostname normalization, IDNA normalization, DNS failure/empty answers, metadata hostnames whose DNS resolves to a forbidden address, and a hostname with one public plus one forbidden answer.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q tests/test_outbound_policy.py`
Expected: FAIL because `core.net.policy` does not exist.

- [ ] **Step 3: Implement the pure policy types and classifiers**

```python
class TrustProfile(StrEnum):
    PUBLIC_UNTRUSTED = "public_untrusted"
    PUBLIC_FIXED = "public_fixed"
    OPERATOR_INTERNAL = "operator_internal"

@dataclass(frozen=True)
class ResponseContract:
    name: str
    max_bytes: int
    content_type_prefixes: tuple[str, ...] = ()

IMAGE = ResponseContract("image", 8 * 1024 * 1024, ("image/",))
JSON_TEXT = ResponseContract("json_text", 16 * 1024 * 1024)
BINARY = ResponseContract("binary", 32 * 1024 * 1024)
```

Implement canonical hostname/IP normalization with `ipaddress`; for public profiles reject any address where public-routable status fails or it is loopback/private/link-local/multicast/unspecified/reserved. `PUBLIC_UNTRUSTED` additionally enforces HTTPS, port 443, no userinfo, GET/HEAD eligibility.

- [ ] **Step 4: GREEN and commit**

Run: `PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q tests/test_outbound_policy.py`
Expected: PASS.

```bash
git add apps/api/core/net tests/test_outbound_policy.py
git commit -m "feat: define outbound trust policy"
```
### Task 2: Pinned sync/async transport, redirects, bounded bodies, and metrics

**Files:**
- Create: `apps/api/core/net/transport.py`
- Create: `apps/api/core/net/outbound.py`
- Modify: `apps/api/core/observability.py`
- Create: `tests/test_outbound_transport.py`
- Modify: `tests/test_observability.py`

**Interfaces:**
- Consumes `ValidatedTarget`, `TrustProfile`, `ResponseContract`, `OutboundError` from Task 1.
- Produces `OutboundResponse(status_code: int, headers: Mapping[str, str], body: bytes)` with `.json()` and `.raise_for_status()`, plus `request()` / `async_request()` for public URLs, `FixedOriginClient`, `AsyncFixedOriginClient`, `OperatorInternalClient`, and `AsyncOperatorInternalClient`.
- `OperatorInternalClient(origin, *, host_header=None, timeout=...)` binds one exact configured origin; request methods accept relative paths only.
- Produces metric helper `record_outbound_request(policy, method, outcome)` with bounded labels.

- [ ] **Step 1: Write RED tests for pinning and Host/SNI preservation**

Inject a fake resolver returning `203.0.113.10` and a fake low-level transport recorder. Assert the transport connection target is the validated IP while the HTTP `Host` and `sni_hostname` remain the normalized original hostname. Add a second resolver answer after validation and assert it is never consulted during the same hop.

- [ ] **Step 2: Write RED redirect and response-bound tests**

Cover public→private redirect blocking before a second connection, public-fixed redirect outside allowlist, redirect loop/4th hop rejection, POST 3xx rejection, `Content-Length` over cap, streamed body over cap, image non-`image/*`, and finite timeout construction capped at 120 s.
- [ ] **Step 3: Run RED**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_outbound_transport.py tests/test_observability.py
```
Expected: new transport/metric tests fail because the implementation does not exist.

- [ ] **Step 4: Implement pinned request execution and manual redirect loop**

Use `httpcore` only inside `transport.py`. Build the request against the validated IP, preserve the original authority in `Host`, set `extensions["sni_hostname"]` for HTTPS, disable environment proxies, stream chunks up to `contract.max_bytes + 1`, and close responses on every failure path. Do not expose raw URLs through `OutboundError.__str__`.

`outbound.py` is the only import surface call sites use. It converts low-level transport failures into bounded `OutboundError.code` values and records one outbound metric outcome per attempt/hop.

- [ ] **Step 5: Add bounded metrics**

```python
OUTBOUND_REQUESTS = Counter(
    "seacommons_outbound_http_requests_total",
    "Outbound HTTP attempts by bounded policy/method/outcome",
    ["policy", "method", "outcome"],
)
```
Normalize unknown values to `other`; accepted outcomes are `success`, `blocked_target`, `invalid_request`, `dns_failed`, `redirect_blocked`, `redirect_limit`, `timeout`, `tls_failed`, `invalid_content_type`, `response_too_large`, and `upstream_error`.
- [ ] **Step 6: GREEN and commit**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_outbound_policy.py tests/test_outbound_transport.py tests/test_observability.py
```
Expected: PASS.

```bash
git add apps/api/core/net apps/api/core/observability.py \
  tests/test_outbound_policy.py tests/test_outbound_transport.py tests/test_observability.py
git commit -m "feat: enforce pinned outbound http transport"
```

### Task 3: Migrate untrusted image extraction and X/Twitter media

**Files:**
- Modify: `apps/api/core/intel/vision.py`
- Modify: `apps/api/core/intel/x_media_utils.py`
- Modify: `apps/api/core/intel/x_media.py`
- Modify: `tests/test_intel_services.py`
- Modify: `tests/test_resolve_x_media.py`
- Modify: `tests/test_backfill_alarm_phone.py`
- Create: `tests/test_outbound_media.py`

**Interfaces:**
- `vision.extract_from_url(url)` keeps returning `dict | None`.
- `x_media_utils.fetch_tweet_photos(tweet_id)` keeps returning `list[str]`.
- `x_media_utils._download_bounded_image(url)` keeps returning `bytes | None`.
- [ ] **Step 1: Write RED SSRF regressions for `/extract-image` and media helpers**

Add route/service tests proving `http://127.0.0.1`, RFC1918, `169.254.169.254`, and a public first hop redirecting to private all return the existing safe `None`/404-style result without opening the forbidden second connection. Include a query token in the hostile URL and assert it is absent from captured logs.

For X media, assert only the existing Twitter/X origins are accepted under `PUBLIC_FIXED`, that a redirect to a non-allowlisted host fails, `_download_bounded_image` rejects non-image and >8 MiB responses, and `fetch_tweet_photos` preserves its current empty-list-on-failure behavior.

- [ ] **Step 2: Run RED**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_outbound_media.py tests/test_resolve_x_media.py \
  tests/test_backfill_alarm_phone.py tests/test_intel_services.py
```
Expected: SSRF/policy assertions fail against the legacy direct clients.

- [ ] **Step 3: Migrate the two acquisition paths**

`vision.extract_from_url()` calls `async_request(..., profile=PUBLIC_UNTRUSTED, contract=IMAGE)` and catches only bounded outbound/upstream failures before returning `None`.

`fetch_tweet_photos()` uses `PUBLIC_FIXED` for `cdn.syndication.twimg.com` with `JSON_TEXT`; `_download_bounded_image()` uses `PUBLIC_FIXED` for the existing `_ALLOWED_MEDIA_HOSTS` with `IMAGE`. Keep `resolve_x_media()` ordering, deduplication, normalization, and diagnostics unchanged.

- [ ] **Step 4: GREEN and commit**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_outbound_media.py tests/test_resolve_x_media.py \
  tests/test_backfill_alarm_phone.py tests/test_intel_services.py \
  tests/test_twikit_monitor.py -k "tweet_media_urls or quote_media"
```
Expected: PASS.
```bash
git add apps/api/core/intel/vision.py apps/api/core/intel/x_media_utils.py \
  apps/api/core/intel/x_media.py tests/test_outbound_media.py \
  tests/test_resolve_x_media.py tests/test_backfill_alarm_phone.py tests/test_intel_services.py
git commit -m "fix: harden untrusted media fetches"
```

### Task 4: Migrate auto-drift and remote drift worker to bound internal origins

**Files:**
- Modify: `apps/api/core/intel/auto_drift_client.py`
- Modify: `apps/api/core/drift/engine.py`
- Modify: `tests/test_auto_drift_client.py`
- Create: `tests/test_outbound_internal.py`

**Interfaces:**
- `request_auto_drift(...) -> bool` remains unchanged for callers.
- `_remote_compute(...) -> DriftResult | None` remains unchanged.
- Both create an `OperatorInternalClient` from trusted configuration before request payload values are applied.

- [ ] **Step 1: Write RED internal-origin tests**

Extend `test_auto_drift_client.py` to prove `API_INTERNAL_URL=http://127.0.0.1:8100` is permitted under `OPERATOR_INTERNAL`, the configured `Host` override is preserved, and request data cannot replace the bound origin (e.g. an event id containing `https://evil.example`).

In `test_outbound_internal.py`, configure `DRIFT_WORKER_URL=http://10.0.0.5:9000`, assert `/compute` is appended as a relative path, `X-Worker-Secret` is preserved, a 3xx is not followed, and any `OutboundError` keeps `_remote_compute` returning `None`.
- [ ] **Step 2: Run RED**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_auto_drift_client.py tests/test_outbound_internal.py
```
Expected: FAIL because both call sites still use direct `httpx`.

- [ ] **Step 3: Implement the migrations**

For auto-drift:
```python
client = OperatorInternalClient(
    config.API_INTERNAL_URL,
    host_header=config.API_INTERNAL_HOST_HEADER or None,
    timeout=10.0,
)
response = client.post("/api/v1/intel/auto-drift", json=body)
```
For remote drift, bind `DRIFT_WORKER_URL`, use `DRIFT_WORKER_TIMEOUT_S` (validated/capped by the outbound layer), POST only `/compute`, and keep the existing in-process fallback.

- [ ] **Step 4: GREEN and commit**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_auto_drift_client.py tests/test_outbound_internal.py \
  tests/test_intel_auto_drift_route.py tests/test_p0_11_drift_authority_cutover.py
```
Expected: PASS.

```bash
git add apps/api/core/intel/auto_drift_client.py apps/api/core/drift/engine.py \
  tests/test_auto_drift_client.py tests/test_outbound_internal.py
git commit -m "fix: bind internal drift http origins"
```

### Task 5: Replace ungoverned PyJWKClient fetching with canonical JWKS acquisition

**Files:**
- Modify: `apps/api/core/security.py`
- Modify: `tests/test_security.py`
- Create: `tests/test_outbound_jwks.py`

**Interfaces:**
- `authenticate_token(token: str) -> Principal` is unchanged.
- `_load_jwks(force_refresh: bool = False) -> dict` keeps a five-minute cache.
- A helper `_signing_key_from_jwks(token, jwks)` selects by JWT `kid` and returns a PyJWT signing key object.
- [ ] **Step 1: Write RED auth/JWKS tests**

Cover: configured loopback/private JWKS origin allowed only through `OPERATOR_INTERNAL`; JWKS body read under `JSON_TEXT`; cache hit avoids network for five minutes; unknown `kid` triggers exactly one forced refresh; still-unknown `kid` fails 401; network/policy/JSON failure fails 401; no test patches `jwt.PyJWKClient` after migration.

Use a generated in-memory RSA/EC JWK fixture or a minimal static public JWK fixture and patch `jwt.decode` only where the test is validating role application rather than cryptography.

- [ ] **Step 2: Run RED**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_outbound_jwks.py tests/test_security.py
```
Expected: FAIL because `authenticate_token()` still delegates network access to `PyJWKClient`.

- [ ] **Step 3: Implement canonical JWKS fetch and key selection**

Bind `_jwks_url()` as an `OperatorInternalClient` exact origin plus relative path, fetch JSON through the canonical client, and preserve the five-minute `_jwks` cache. Decode the JWT header with `jwt.get_unverified_header(token)`, match `kid`, convert the JWK with `jwt.PyJWK.from_dict(...).key`, then call `jwt.decode(...)` with the existing algorithms/audience/issuer/options.

On unknown `kid`, clear/refresh once and retry key selection. Do not fall back to `PyJWKClient`.

- [ ] **Step 4: GREEN and commit**

Run Step 2. Expected: PASS.

```bash
git add apps/api/core/security.py tests/test_security.py tests/test_outbound_jwks.py
git commit -m "fix: govern oidc jwks acquisition"
```
### Task 6: Migrate forensic witness fan-out without exposing configured endpoints

**Files:**
- Modify: `apps/api/core/forensic/logger.py`
- Create: `tests/test_forensic_outbound.py`

**Interfaces:**
- `_broadcast(packet)` remains best-effort and returns `None`.
- `_parse_witness_endpoints(raw)` remains compatible with JSON-list and comma-separated forms.
- Each configured endpoint is converted to one `OperatorInternalClient`; packet data never supplies an origin.

- [ ] **Step 1: Write RED tests**

Test one loopback/private witness URL succeeding through a fake canonical transport, two witnesses where the first times out and the second still receives the packet, 3xx not followed, and a query-bearing configured endpoint whose secret query text never appears in logs. Assert success logs use only a bounded ordinal/status such as `witness=1 status=204`, not the endpoint.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q tests/test_forensic_outbound.py`
Expected: FAIL because `_broadcast()` still calls `requests.post` and logs raw endpoints.

- [ ] **Step 3: Implement migration**

Parse each trusted configured endpoint once into exact origin plus relative path/query. Bind the origin to `OperatorInternalClient`, POST the packet to the preserved relative target with a 5 s finite timeout, disable redirects, and catch `OutboundError`/upstream failures per witness so fan-out continues.

- [ ] **Step 4: GREEN and commit**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_forensic_outbound.py tests/test_forensic_link.py
```
Expected: PASS.

```bash
git add apps/api/core/forensic/logger.py tests/test_forensic_outbound.py
git commit -m "fix: govern forensic witness egress"
```
### Task 7: Legacy exception inventory, CI adoption guard, docs, and release qualification

**Files:**
- Create: `docs/security/legacy-outbound-http.json`
- Create: `scripts/check_outbound_http_bypasses.py`
- Create: `scripts/validate_outbound_internal_config.py`
- Create: `tests/test_outbound_adoption_guard.py`
- Create: `tests/test_outbound_config_validation.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/TESTING.md`
- Modify: `docs/current_work.md`
- Modify: `prompt.md`
- Create: `apps/web/public/security/outbound-smoke.svg` (static, non-sensitive release-smoke asset; no application behavior)
- Modify: this plan to check completed steps and record evidence.

**Interfaces:**
- Inventory records exact `{path, callee, count}` entries for legacy direct HTTP calls under `apps/api/core/**` that remain after Tasks 3–6.
- Scanner uses Python AST, recognizes direct `httpx` module calls/client constructors, `urllib.request.urlopen`/imported `urlopen`, and `requests` module/session calls, then compares actual counts to the checked-in inventory.
- CI executes the scanner as a blocking repository/security step; it never writes or auto-updates the inventory.

- [ ] **Step 1: Write RED guard tests**

Create fixture source snippets in `tests/test_outbound_adoption_guard.py` proving an inventoried `(path, callee, count)` passes, a new file/callee fails, an extra call of an already-inventoried callee fails by count, and canonical `core.net` code is not falsely classified when it contains no direct legacy client call.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q tests/test_outbound_adoption_guard.py`
Expected: FAIL because the scanner/inventory do not exist.

- [ ] **Step 3: Implement scanner and manually snapshot remaining legacy calls**

The script exits non-zero and prints only reviewable path/callee/count deltas. Build `legacy-outbound-http.json` from the post-migration tree by inspecting each remaining call; do not add any Task 3–6 migrated path as an exception and do not add wildcards.

Add to the `repository` CI job:
```yaml
- name: reject new direct outbound HTTP bypasses
  run: python scripts/check_outbound_http_bypasses.py
```
- [ ] **Step 4: Update controller/testing docs**

Document Packet J as active while implementation is in progress, list the remaining hardcoded collector batches explicitly, and state that WebSocket URL policy remains out of scope. `docs/TESTING.md` must add the outbound policy/transport/adoption suites to the security pyramid and record that they require no live Internet.

- [ ] **Step 5: Run focused security release gates**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q \
  tests/test_outbound_policy.py tests/test_outbound_transport.py \
  tests/test_outbound_media.py tests/test_outbound_internal.py \
  tests/test_outbound_jwks.py tests/test_forensic_outbound.py \
  tests/test_outbound_adoption_guard.py tests/test_auto_drift_client.py \
  tests/test_security.py tests/test_observability.py
apps/api/.venv/bin/ruff check apps/api tests scripts --select E9,F63,F7,F82
PYTHONPATH=apps/api apps/api/.venv/bin/python scripts/check_outbound_http_bypasses.py
git diff --check origin/main..HEAD
```
Expected: all PASS.

- [ ] **Step 6: Run full exact-head gates**

Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q
(cd apps/api && .venv/bin/mypy core/net core/intel/vision.py core/intel/x_media_utils.py \
  core/intel/x_media.py core/intel/auto_drift_client.py core/drift/engine.py \
  core/security.py core/forensic/logger.py --follow-imports=skip)
(cd apps/api && .venv/bin/python -m pip_audit . --strict)
(cd apps/web && npm test && npm run lint && npm run build && npm audit --omit=dev --audit-level=high)
(cd apps/edge && npm test && npx wrangler deploy --dry-run && npm audit --omit=dev --audit-level=high)
```
After pushing the exact implementation head, require all GitHub Full CI jobs and CodeQL to pass before merge. Do not call the packet complete from local or focused tests alone.

- [ ] **Step 7: Validate production configuration without revealing configured origins**

Create `scripts/validate_outbound_internal_config.py`. It loads runtime config, validates/binds `API_INTERNAL_URL`, optional `DRIFT_WORKER_URL`, the effective OIDC JWKS/issuer origin, and every witness endpoint with `OPERATOR_INTERNAL`, and prints only lines shaped like `API_INTERNAL_URL valid http` or `OIDC_JWKS invalid https`. It must never print hostname, IP, port, path, query, credentials, headers, or exception text.

Add `tests/test_outbound_config_validation.py` proving secrets/hosts are absent from both success and failure output. Run:
```bash
PYTHONPATH=apps/api apps/api/.venv/bin/pytest -q tests/test_outbound_config_validation.py
PYTHONPATH=apps/api apps/api/.venv/bin/python scripts/validate_outbound_internal_config.py
```
Expected: tests PASS; production command exits 0 only when every configured internal origin is valid under its bound operator policy.

- [ ] **Step 8: Production smoke after merge/restart**

Deploy the static `https://live.seacommons.org/security/outbound-smoke.svg` asset. Verify `/health` and `/ready`; POST that URL to the public `extract-image` route and expect the existing no-coordinate 404 while the local `/metrics` outbound counter records `policy="public_untrusted",outcome="success"`; then POST `http://127.0.0.1:8100/health` and confirm the outbound counter records `blocked_target` without a second connection. Confirm auto-drift/internal API still succeeds. If remote drift/JWKS/witness are configured, verify their existing health/behavior without printing private endpoints or credentials. No destructive mutation or new capture is introduced.

- [ ] **Step 9: Final exact-diff review and commit controller evidence**

Review spec-to-HEAD for accidental semantic changes, raw URL logging, unrestricted redirects, hidden legacy fallbacks, new direct client bypasses, and sensitive test fixtures. Fix Critical/Important findings, rerun affected gates, update controllers with exact implementation SHA/CI/production evidence, then merge/push.

```bash
git add .github/workflows/ci.yml apps/api/core/net apps/api/core/observability.py \
  apps/api/core/intel apps/api/core/drift/engine.py apps/api/core/security.py \
  apps/api/core/forensic/logger.py scripts/check_outbound_http_bypasses.py \
  scripts/validate_outbound_internal_config.py apps/web/public/security/outbound-smoke.svg \
  docs/security/legacy-outbound-http.json docs/TESTING.md docs/current_work.md prompt.md tests
git commit -m "feat: enforce outbound http trust boundary"
```
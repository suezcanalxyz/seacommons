# Tradecraft capability matrix

2026-11-06: Evidence reproducibility via npm lockfile and advisory lineage: OBSERVED build-security control (#447), pending CI and live. Maritime attack competing hypotheses: EXPERIMENTAL (#440), no validated benchmark. Sentinel SAR GEOINT: EXPERIMENTAL (#431), scene-disjoint validation pending. Lawful radio evidence: UNSUPPORTED end-to-end until rights/coverage audit. Humanitarian follow-up and drift: EXPERIMENTAL (#367), redacted real-case E2E pending. Taxonomy does not imply operational capability.

2026-11-06 E-AIS-TXN-02: Intelligence evidence preservation / chain of custody = EXPERIMENTAL: canonical AIS prune has lock and checksum verification, now guarded by transaction-scope structural regression in #452. Not OBSERVED end-to-end: concurrent writer, R2 replay and independent manifest/restore remain untested. Public maritime incident attribution = UNSUPPORTED without adjudicated #440 corpus. No change to humanitarian privacy posture.

2026-11-06 E-AIS-FAILCLOSED-03: evidence preservation failure handling EXPERIMENTAL, structural guard added for corruption/partial delete exception propagation; runtime atomicity and restore UNSUPPORTED until real DB/R2 failure injection. No new OSINT/GEOINT capability claimed.

2026-11-06 | AIS retention-input validation | EXPERIMENTAL (not operational): explicit positive integer guard in TrackStore.prune, hard negatives 0/-1/-365/True/0.5. Primary doctrine: fail-closed input validation; no evidence deletion enabled. Observed: source commit 8aea189; tests added 9c242dd; CI/restore not yet confirmed. No public capability claimed.

- 2026-11-06: AIS evidence-preservation engineering — **experimental**. Seven isolated regression tests passed against exact PR-head source on VM; no concurrent PostgreSQL or restore drill, hence not observed operational capability.

2026-11-06 | Evidence preservation / integrity (AIS): EXPERIMENTAL. New deterministic gzip v1 roundtrip and bit-flip negative-control fixture PR #452 commit d24b781; CI pending. NOT OBSERVED: real PostgreSQL two-writer isolation, object-store restore, manifest chain-of-custody and production archival release.

2026-11-06 | AIS archival evidence preservation: EXPERIMENTAL. E-AIS-FAULT-05 now observes fail-closed R2 GET outage in executable isolated transaction harness, 9/9 local tests; still UNSUPPORTED: proven two-session PostgreSQL race and full R2 restore drill. Do not activate retention.

2026-11-06 | Evidence integrity / chain of custody | EXPERIMENTAL | P0 #335 PR #452 commit 80d8c629: regression verifies readback checksum mismatch is a raising branch inside the SQL transaction. Local 10/10 tests passed. NOT OBSERVED: real concurrent PostgreSQL transaction and R2 restore durability. No claim of operational archive safety.

2026-11-06 21:04 Africa/Tunis | Evidence preservation / all-source chain of custody | EXPERIMENTAL: executable corrupted-readback fault injection against canonical prune, expects SQL rollback and zero DELETE; not OBSERVED in production. Unsupported: concurrent-writer proof, durable R2 restore and end-to-end recovery. No new source collection or private data.

2026-11-09 | Intelligence evidence chain-of-custody / AIS archive recoverability | EXPERIMENTAL. OBSERVED: #457 PostgreSQL disposable lock gate merged (9e19abf3), Vercel production READY for that commit (not a functional archive smoke). NOT OBSERVED: R2 conditional-write retry, canonical prune concurrent writer, restored full-row equivalence. UNSUPPORTED: any claim of safe production AIS retention. Required benchmark: E-AIS-R2-08. Source https://developers.cloudflare.com/r2/reference/consistency/ (2026-10-14). Humanitarian data out of scope.

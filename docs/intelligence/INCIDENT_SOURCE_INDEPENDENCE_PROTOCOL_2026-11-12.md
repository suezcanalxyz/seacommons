# Incident source-independence negative-control protocol (2026-11-12)

Links: #431 #440. **Status: experimental specification, not deployed capability.** No incident attribution, new collection, or production data change.

## Research question
Can an incident-corroboration evaluator distinguish *two independent primary reports* from *two republications of the same original claim*, without using AIS silence as attack evidence?

## Tradecraft and primary references
- [Berkeley Protocol on Digital Open Source Investigations](https://www.ohchr.org/en/publications/policy-and-methodological-publications/berkeley-protocol-digital-open-source), OHCHR / Human Rights Center, 2022. Source verification, preservation, provenance and investigator safety. Accessed 2026-11-12. Publication available publicly; **reuse license not verified**, so do not copy text or datasets. **Adopt** provenance requirements, not a third-party incident feed.
- [W3C PROV-O](https://www.w3.org/TR/prov-o/), W3C Recommendation, 2013. Entities, activities and agents for derivation lineage. Accessed 2026-11-12. W3C document license/terms apply; **no external data ingestion**. **Pilot** a small internal lineage graph rather than add a database.
- [NIST AI RMF 1.0](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf), NIST, 2023, DOI [10.6028/NIST.AI.100-1](https://doi.org/10.6028/NIST.AI.100-1). Validation, transparency and risk management. Accessed 2026-11-12. US government publication; verify individual redistribution terms. **Adopt** risk-based abstention metrics.
- [IMO GISIS maritime security](https://gisis.imo.org/), IMO, official portal; coverage, access rights and license for any particular dataset **not verified**. **Do not ingest** until terms and availability are checked.

## Experiment / negative controls
Use **synthetic, non-identifying** fixtures, no real humanitarian coordinates:
1. Primary A reports an explosion at time T; news B and aggregator C repeat A. Expected: **one** independent origin, not corroborated.
2. Primary A and independent primary D report the same event, with compatible event time and location uncertainty. Expected: **two** origins, eligible for review but not automatic attribution.
3. Two independently authored reports disagree on vessel identity. Expected: conflicting identity, abstain.
4. AIS gap coincides with an unverified social post. Expected: no attack assertion; candidate/unresolved only.
5. Report timestamp is later than claimed event time; distinguish event, publication and ingest timestamps.
6. Humanitarian distress record accidentally enters maritime-security set. Expected: reject cross-domain fusion and avoid public sensitive geometry.

### Measurement and acceptance
- Source-independent origin count (not URL count), 100% correct across six synthetic controls.
- False automatic perpetrator attributions = 0; AIS-gap-only attacks = 0.
- Every published claim has derivation lineage and explicit uncertainty, or abstains.
- Benchmark future real corpus: >=20 reviewable incidents plus >=20 hard negatives as #440 requires, separately human-adjudicated.
- Record precision, recall, false alerts / 100 candidates, abstention and lineage completeness. No fabricated baseline: **baseline not yet measured**.

### Implementation owner / integration
Use existing MaritimeEpisodeDB and InvestigationHypothesisDB and canonical incident evidence adapters; no parallel source-of-truth table. Add a pure lineage-normalization function and tests to the existing incident benchmark package after auditing its paths. Compare by canonical origin identity and documented syndication relationship; URL/domain diversity alone does not prove independence. Store raw references without republishing protected material.

### Cost, privacy, rollback
Synthetic fixture test: negligible infrastructure cost, no provider quotas. Real source acquisition requires separate terms/privacy review. Rollback: revert this documentation PR; later code change behind feature flag. **GREEN docs only**, not evidence of a production feature.

### Release gate
Do not merge code or deploy incident claims based on this spec. For any later GREEN implementation: exact-HEAD CI, security/privacy and negative controls, deploy via canonical pipeline, public smoke with SHA+URL; AMBER for publication policy changes. Next research question: how to represent syndicated source lineage when upstream metadata is missing without overclaiming independence?

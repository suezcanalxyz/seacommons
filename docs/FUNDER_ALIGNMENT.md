# Funder alignment: editorial and release notes

3 October 2026. Scope: institutional site and a new ten-slide web funding brief.

## Brief and editorial decisions

The user reports that Glocal Impact Network has identified potential sponsors
or funders and requests a more structured presentation of SeaCommons. Funder
identities and investment terms are unknown. This contextual report is not an
endorsement or a funding commitment and is deliberately absent from public copy.

Preserve the navy/azure visual identity, film hero, typography and restrained
motion. Add a project brief, funding workstreams, a proposed pilot schedule,
evaluation measures and clear next steps. Constrain long-form content width for
legibility. Leave operational data contracts and incident semantics unchanged.

The review discipline inspired by the user's Ethos training separates:

| Review dimension | Acceptance criteria |
| --- | --- |
| Content | Purpose, intended users, available evidence, limits, delivery and funding decision are explicit. |
| Factual accuracy | Proposed milestones are labelled. No invented impact totals, adoption, endorsements, ROI or fundraising amount. |
| Structure | Site opens with a project brief. Deck progresses from problem through method and current stage to pilot, evaluation and funding decision. |
| Layout | Consistent margins and readable text. No horizontal overflow on mobile, no slide clipping at desktop or print size. |
| Aesthetics | Existing brand and artistic identity remain legible without obscuring the funding proposition. |
| Overall usefulness | A reader can identify what support would fund and how to evaluate delivery. |

Do not assign self-generated quality scores. Evidence for one dimension does
not establish quality in another. Attractive slides cannot establish traction.

## Claims and provenance

| Public statement | Basis | Qualification |
| --- | --- | --- |
| Open-source maritime evidence infrastructure | Repository licence, source code and `apps/web/src/docs/content/SEACOMMONS.md` | Software availability is not proof of operational effectiveness. |
| Public Live, archive and docs surfaces | Existing site routes and components | Current health remains a deployment check. |
| Proposed six-month pilot | New proposal authorised by the user's funding realignment brief | Subject to scope, funding and participant agreement. |
| Intended user groups | Research and humanitarian purpose in project documentation | Adoption is to be evaluated. |
| Technical delivery by Matteo Messina | User context and existing suezcanal.xyz attribution | Contracting entity and other roles require agreement. |
| Funding work and evaluation measures | Prospective scope defined in this change | No achieved results or targets are claimed. |

## Presentation source

- `apps/web/funding.html` is the build entry.
- `apps/web/src/site/funding-main.jsx` defines ten slides.
- `apps/web/src/site/fundingContent.js` shares workstreams, schedule and metrics
  between the site and deck.
- `docs/FUNDING_BRIEF.md` is a readable proposal for review and reuse.
- Public path after deployment: `/funding.html`. Print styles use a 16:9 page.

No existing deck was found in this repository. This is a new base presentation,
not a claimed edit of a file held elsewhere.

## Deployment and VM handover

GitHub changes are prepared in a PR. Vercel may create a branch preview through
the existing integration. Production deployment and VM alignment are deferred
until the change is reviewed and the SSH key is available.

When authorised to align the VM:

1. Confirm the approved commit and current VM revision. Preserve local changes.
2. Build and serve the same multi-page web package, including `funding.html`.
3. Ensure the existing proxy serves `/funding.html` as a static document, not
   as the console fallback. No backend migrations are needed for this change.
4. Check homepage, deck, docs and system status, then Live and archive routes.
5. Keep the previous web release available for rollback.

The repository's AI engineering policy requires human review before merge.
The PR records performed checks and remaining review requirements.

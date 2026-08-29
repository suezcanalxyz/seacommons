# SeaCommons — brand strategy

This document is the source of truth for positioning, voice, color semantics and
motion rules across the public site (`apps/web/src/site/`) and the operator
console (`apps/web/src`). It exists so branding decisions don't get re-litigated
implicitly, one component at a time, in future UI work.

## Positioning

SeaCommons is a single master brand with a **modular service portfolio** — it
does not hide its full capability set behind a purely humanitarian front. The
site publicly describes every service family it provides:

- **Fusion** — multi-source normalisation of maritime distress signals, drift
  simulation. The founding, most-developed capability.
- **MDA** (Maritime Domain Awareness) — vessel identity/spoofing detection,
  shadow-fleet correlation, sanctions/grey-zone corroboration, chokepoint and
  infrastructure analytics. Described publicly (`apps/web/src/site/sections/MDA.jsx`)
  at a methodological level; no operational data or live case detail is exposed
  outside the OPERATIONAL/O2 access tier.
- **Engine** — physically calibrated Unreal renderer for the same drift-scene
  record used by Play.
- **Surfaces** — Play (public/synthetic demo), Live (public, privacy-filtered
  feed), Console (operator, authenticated).

There is one wordmark, one palette, one typographic system across all of this.
Modules are distinguished by label/copy, never by a dedicated identity color —
see Color semantics below for why.

## Voice

Formal, epistemic, never promotional. Every public-facing section — including
MDA — talks about *what is detected and under what evidentiary guarantee*
(corroboration required, human review boundary, confidence not verdict), not
about capability in intel-marketing terms. Reuse the vocabulary already
established in Governance/SystemView: uncertainty, provenance, contestability,
correction by design, dual-use assessment.

The console's functional UI copy (labels, badges, tooltips) can stay dense and
technical — it's operational UI, not marketing — but it shares the same color
and typography system as the site.

## Palette — dark navy, azure brand accent

Original identity was a dark green-black surface with a lime-green brand
accent. Both read as "green," which the founder rejected outright — the
surface and the brand accent are now both in the navy/blue family (no lime,
no green, anywhere):

- **Surface** (`--sc-ink-900` … `--sc-ink-700`, `apps/web/src/ui/ui.css`): dark
  navy ramp (`#060a14` → `#111f3b`), replacing the old green-black ramp
  (`#04100d` → `#143029`). Applies to the site, the console (`suez-theme.css`,
  `body` background), and every hardcoded panel/card background that used to
  match the old ramp by literal hex.
- **Brand accent**: the token formerly named `--sc-lime` (`#c8ff3d`) is now
  `--sc-brand` (`#33c7ff`, azure). Same role — CTA, wordmark, focus ring,
  primary emphasis — never a status color. Every `var(--sc-lime*)` and every
  hardcoded `rgba(200, 255, 61, …)` literal across `ui.css`, `site.css`,
  `suez-theme.css`, `site.html`, `index.html` and the `Threads` WebGL color
  prop was repointed to `--sc-brand` / `rgb(51, 199, 255)`.

Card/tile border tones used for visual rhythm (e.g. `.wp-card--blue/lime/paper/amber`
in Programme and MDA sections, `.env-card--lime/paper/sea` in Environments) keep
their existing slot names (`--lime` etc.) as arbitrary variant identifiers —
renaming those is pure naming hygiene with no visual effect, since the
underlying `var(--sc-brand)` they resolve to already carries the new color.

## Status colors — fixed, brand-wide

Also defined in `apps/web/src/ui/ui.css`, distinct from the brand accent above.
Reused identically on the site (live signal strip, stat bands) and in the
console (MDA/intel severity badges, alerts). A module is never assigned one of
these as its identity color — if e.g. rose were "the MDA color," every MDA
badge would read as critical even when nominal, which breaks the one thing a
severity system has to do reliably.

| Token | Meaning | Never used for |
|---|---|---|
| `--sc-brand` | Brand / call-to-action (azure) | Status or severity |
| `--sc-sea` | Nominal / secondary / live-ok | Alerts |
| `--sc-blue` | Informational | Severity |
| `--sc-amber` | Uncertainty / warning | Brand identity |
| `--sc-rose` | Critical / alert | Decorative use |

Applied in `src/styles.css` to `.mda-sev--*`, `.intel-sev--*`, `.osint-stat--*`
(previously hardcoded hex, now pointing at these tokens).

## Motion budget

Hero motion is calibrated down to match the sober register of the rest of the
site: `ShinyText` no longer loops continuously in the hero kicker (`static`
prop), `Threads` runs at reduced amplitude/count, and `Magnetic` is reserved
for the primary CTA only. Every other section already used `Reveal` /
`SpotlightCard` / `TiltCard` / `AnimatedNumber` sparingly and needs no change.

New motion is justified by content change (e.g. the live signal strip
updating with real data), never added as decoration on its own.

## Live signal strip

`apps/web/src/site/LiveSignalStrip.jsx` sits directly under the header (above
Hero, `SiteApp.jsx`) and shows the latest public distress signals from
`GET /api/v1/live/signals`, click-through to `live.seacommons.org`. It
degrades to a neutral message on empty/error state, never a visible error or
infinite spinner, and exposes no more than the existing privacy-filtered
public payload.

## Logo

The current brandmark (`BrandMark` in `chrome.jsx`) is a placeholder pair of
dots. Designing a real mark is out of scope for engineering work — it needs
human visual judgment — but the markup is structured so it can be swapped
without a surrounding refactor.

# Play ALL Timeline + Mobile Live Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Play open as an archive-wide ALL map with optional temporal filtering, and make Live selected-case panels readable on mobile.

**Architecture:** Play keeps one global mode state: `all` or `temporal(cutoff)`. ALL renders the archive point collection without a cutoff; dragging the global timeline activates a cutoff and recomputes visible incidents/evidence. Mobile Play is map-first with optional drawer/bottom-sheet. Live mobile replaces the oversized floating detail modal with a split viewport: upper map, lower full-width scrollable report.

**Tech Stack:** React, MapLibre GL, CSS media queries, Vite/Vitest.

**Spec:** `docs/superpowers/specs/2026-09-05-play-all-timeline-mobile-design.md`

## Global Constraints

- No Cesium/Unreal dependency path in public Play.
- ALL is the initial Play state and rightmost timeline position.
- Temporal mode must never reveal evidence after the selected cutoff.
- Mobile layouts must not horizontally overflow at 390-430 px.
- No backend schema migration is required for this UI tranche.

---

### Task 1: Play global ALL/temporal state
**Files:** Modify `apps/web/src/features/play/PlayTimeline.jsx`, `apps/web/src/features/play/timeline.js`; Test `apps/web/src/features/play/timeline.test.js`.
**Interfaces:** Produce helpers that map a global slider position to `all | cutoff` and filter incidents/timeline items by cutoff.
- [ ] Write tests proving initial/rightmost position is ALL and a prior position returns a cutoff.
- [ ] Run the focused test and confirm RED.
- [ ] Implement the minimal pure helpers.
- [ ] Run the focused test and confirm GREEN.
- [ ] Commit.

### Task 2: Play ALL archive map + temporal rendering
**Files:** Modify `apps/web/src/features/play/PlayTimeline.jsx`; Test `apps/web/src/features/play/PlayTimeline.test.jsx` if present, otherwise extend pure timeline tests around map-data derivation.
**Interfaces:** ALL renders all incident points; temporal mode renders only incidents/evidence known at or before cutoff.
- [ ] Write failing derivation tests for ALL and cutoff views.
- [ ] Confirm RED.
- [ ] Implement map-data derivation and global timeline control.
- [ ] Confirm GREEN.
- [ ] Commit.

### Task 3: Play mobile map-first UX
**Files:** Modify `apps/web/src/features/play/play.css`, `apps/web/src/features/play/PlayTimeline.jsx`; Test with CSS/DOM contract tests already used by web test suite.
**Interfaces:** On <=680px, cases become a toggleable drawer and evidence becomes a bottom sheet; map is the primary viewport.
- [ ] Add a failing DOM/CSS contract test for mobile drawer/sheet classes and ALL label.
- [ ] Confirm RED.
- [ ] Implement mobile drawer, case sheet, and responsive CSS without horizontal overflow.
- [ ] Confirm GREEN and run build.
- [ ] Commit.

### Task 4: Live mobile selected-case split layout
**Files:** Modify `apps/web/src/styles.css` and the Live detail component(s) that own `.cone-panel`; Test existing live/map frontend tests plus a focused layout contract test.
**Interfaces:** Selected case on mobile reserves upper map area and places detail sheet below, full-width and independently scrollable.
- [ ] Add a failing CSS/DOM contract test for mobile selected-case layout.
- [ ] Confirm RED.
- [ ] Implement the split layout and stacked metadata rows.
- [ ] Confirm GREEN.
- [ ] Commit.

### Task 5: Verification and rollout
**Files:** No feature code unless a verification failure requires a fix.
- [ ] Run web lint/typecheck, all web tests, and unified build.
- [ ] Run backend focused Play/Live API tests to ensure no contract regression.
- [ ] Push branch, open PR, wait for required CI/CodeQL gates, merge only when green.
- [ ] Verify Vercel production deploy reaches merged SHA.
- [ ] Smoke `play.seacommons.org` and `live.seacommons.org` on mobile-sized viewport contracts and public APIs.
- [ ] Confirm Alarm Phone source health separately from UI visibility.

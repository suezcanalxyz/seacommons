# UI/UX Redesign — Mobile Map-First Interface (June 2026)

## Summary

The console now has two distinct layout modes sharing one component tree:

- **Desktop (>680px)** — unchanged interaction model: floating left sidebar with
  Sim / Live / OSINT / Config tabs, chevron toggle, map fills the viewport.
  Visual polish only (consistent corner radii, hover/active states, focus rings).
- **Mobile (≤680px)** — full-screen map with a **bottom tab bar**
  (Map · SAR · Live · OSINT · Config). Panels open as a **bottom sheet** covering
  the lower ~62% of the screen, keeping the map visible and interactive above it.

## Files

| File | Change |
|---|---|
| `apps/web/src/hooks/useIsMobile.js` | **New.** Reactive `matchMedia('(max-width: 680px)')` hook — single source of truth for the JS-side breakpoint, mirrors the CSS breakpoint. |
| `apps/web/src/components/BottomNav.jsx` | **New.** Mobile tab bar. Inline SVG icons (no icon lib). `Map` dismisses the sheet; re-tapping the active tab toggles it closed. OSINT tab shows an event-count badge. |
| `apps/web/src/main.jsx` | Renders `BottomNav` (mobile) vs the chevron toggle (desktop); sheet starts **closed** on mobile so the map is the landing experience; map click handlers no longer auto-open the panel on mobile (it would cover the point just flown to); bottom-sheet grab handle added to the sidebar. |
| `apps/web/src/styles.css` | Mobile media query rewritten: sidebar → bottom sheet (`translateY` transitions, rounded top, shadow), all map furniture (cone panel, case log, overlays, banners) repositioned above the tab bar via `--nav-h`, 16px inputs (prevents iOS focus zoom), ≥42px touch targets, `dvh` units + `env(safe-area-inset-bottom)`. Desktop additions: focus-visible rings, hover/active button states, unified 4px card radii. |
| `apps/web/index.html` | `viewport-fit=cover` (notch safe-areas) + `theme-color`. |

## Behavior contract (mobile)

- Tab bar is always visible; the sheet slides over the map but **under nothing**.
- `Map` tab, the grab handle, and re-tapping the active tab all close the sheet.
- Tapping an intel event or vessel on the map keeps the sheet closed so the
  flyTo target stays visible (handlers check the media query at event time
  because they are registered once at map init).
- A critical/high distress event arriving over WebSocket still force-opens the
  OSINT panel (deliberate — it demands attention).

## Robustness fixes shipped alongside (no behavior change)

1. **Stale vessel expiry** (`main.jsx fetchVessels`): vessels absent from every
   incremental diff for 30 min are dropped from the merged snapshot — previously
   they stayed painted until a full page reload.
2. **Debounced nearest-vessel lookup**: lat/lon inputs no longer fire
   `/api/v1/vessels/nearest` on every keystroke (400 ms settle).
3. **Null guard** in `loadWeatherGridForMap` — the Live-tab "Refresh overlay"
   button crashed if pressed before map init.
4. `inputmode="decimal"` on lat/lon fields (numeric keypad on mobile),
   EN-only UI string fix ("Apri pannello drift" → "Open drift panel").

## Verified

- `npm run build` clean (vite 6, 39 modules).
- Playwright headless QA at 390×844 and 1440×900:
  - mobile landing = full-screen map + tab bar, sheet closed;
  - SAR/OSINT sheets open with map visible above; handle/Map-tab/re-tap all close;
  - desktop renders no tab bar, sidebar + chevron unchanged.

## Known follow-ups (deliberately not bundled)

- Auth/rate-limiting on `POST /api/v1/alert`, `/intel/manual`, `/intel/auto-drift`.
- Replace hardcoded backend IP in `vercel.json` rewrites with an env-based host.
- Decompose `main.jsx` (state/hooks/panels) — tracked since May audit.
- Remove dead deps from `apps/web/package.json`: `express`, `leaflet`,
  `@types/leaflet`, `@google/genai`, `dotenv`, `motion`, `lucide-react`.
- Swipe-down gesture on the sheet (currently tap-to-close only).

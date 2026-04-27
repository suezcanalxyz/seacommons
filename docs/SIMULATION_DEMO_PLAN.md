# suezcanal.xyz Simulation Demo Plan

## Intent

This visual drift simulation should become a core demonstration surface for `Datum`, not just a landing-page animation.

The current direction is strong:

- white field, light grid, reduced technical UI
- live drift line with weather-driven irregularity
- search cones scaled to the active trajectory
- SAR interception layer
- compact viewport telemetry

This graphic language should be expanded into a modular demo system.

## Current Strengths

- The scene reads as operational software without needing a map.
- The trajectory is legible and works as an abstract maritime model.
- The SAR layer already suggests retasking and interception logic.
- The visual system is strong enough to support product storytelling and technical explanation.

## Current Limitation

The interception model is not yet realistic enough.

Right now the SAR point visually chases the distress point, but the meeting logic is still presentational. It does not yet behave like a proper interception model with:

- own speed and heading constraints
- delayed retasking
- continuous pursuit or lead-pursuit logic
- route correction under changing sea state
- explicit predicted intercept solution
- realistic convergence or missed intercept behaviour

This is the main part that should be upgraded next.

## Development Direction

The simulation should be split into reusable layers:

1. Base drift engine
- distress origin
- weather forcing
- current and wave influence
- evolving trajectory

2. Search geometry
- 6h / 12h / 24h cones
- uncertainty growth
- horizon labels tied to path distance

3. SAR interception
- rescue asset insertion
- retask event
- pursuit line
- predicted intercept
- live ETA / ETS
- merge, miss, or re-route outcome

4. Explanation UI
- compact telemetry chips
- optional step-by-step labels
- switchable annotation mode for demo use

## What The Demo Should Become

This simulation should support multiple demo modes built from the same visual engine:

- distress to drift
- weather update changes route
- search cone expansion
- SAR retask and intercept
- uncertainty growth under worsening weather
- multiple asset comparison
- forensic replay of an event chain

## Recommended Technical Refactor

The current inline animation should become a small simulation module:

- `sim-engine.js`
- `sim-scenes.js`
- `sim-renderer.js`
- `sim-controls.js`

Each scene should run from structured state, not hardcoded visual values.

Suggested state model:

- `distress`
- `weather`
- `drift_path`
- `cones`
- `sar_assets`
- `intercept_prediction`
- `eta`
- `timeline_events`

## Immediate Next Upgrade

Replace the current SAR encounter model with a more realistic pursuit model:

- asset starts from a defined position and speed
- distress keeps drifting independently
- rescue route updates against the live distress position
- optional lead-pursuit mode predicts a future intercept point
- ETA is computed from remaining route, not just visual distance
- final behaviour can resolve to:
  - successful intercept
  - near miss
  - delayed arrival
  - forced re-route after weather shift

## Product Use

This visual language should be treated as a demo asset for `Datum`.

It is suitable for:

- landing presentation
- technical explanation
- investor / partner walkthroughs
- operational concept demonstrations
- scenario playback

## Status

Keep the current simulation and graphic language as the base version.

Do not simplify it back.

Instead, evolve it into the canonical `Datum` demo surface.

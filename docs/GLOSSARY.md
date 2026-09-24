# Glossary

Plain-language definitions for labels used in the SeaCommons Live interface.
For how the pipeline produces them, see [Data flow](DATA_FLOW.md) and the
[Public documentation contract](PUBLIC_DOCUMENTATION.md).

Last reviewed: 2026-09-24, against the current docs and Live UI.

A label describes what SeaCommons received or derived. It does not mean an
incident is confirmed, and it never means intent or wrongdoing.

## Categories

Every public case belongs to one of two families.

### Humanitarian

Cases about people in distress, rescue activity and what happened next, for
example distress, rescue, missing, shipwreck and pushback. The Live legend shows
these as a Humanitarian family. Live uses category-specific colors and marker
styles rather than one universal Humanitarian color. Humanitarian privacy comes
before map precision, so a marker may be approximate.

### Maritime

Cases about vessel behaviour, identity, navigation and other activity, for
example AIS gaps, position integrity, rendezvous, loitering and navigation
safety. Live uses category-specific colors and marker styles rather than one
universal Maritime color. A Maritime label names the type of investigation. It
is not an accusation.

## Terms

### AIS

- **What it is:** Automatic Identification System, the position and identity
  reports that vessels broadcast. SeaCommons uses AIS for vessel tracks,
  coverage checks and anomaly detectors.
- **Observation or inference:** A received AIS report is an observation. Gap,
  position-integrity and loitering labels built from AIS are inferences.
- **Does not establish:** An incident. One AIS broadcast is one source, however
  many providers relay it, so it is never counted as independent corroboration.
  AIS alone cannot confirm a rescue.

### AIS gap

Shown in Live as "AIS reporting gap / dark candidate".

- **What it is:** A vessel that stops appearing in AIS data for a period.
- **Observation or inference:** The silence is an observation. SeaCommons treats
  it as a vessel-specific gap only when nearby vessels kept reporting. If nearby
  traffic went quiet at the same time, it is a coverage gap (a reception outage),
  not a vessel event.
- **Does not establish:** Intent. Missing positions can come from coverage,
  reception or equipment as well as deliberate behaviour.

### Dark activity

- **What it is:** Wording for a vessel that is not visible in AIS where it might
  be expected. In Live it appears as "AIS reporting gap / dark candidate" and as
  "Possible dark vessel", which is a satellite detection with no matching AIS
  signal in the area.
- **Observation or inference:** Both are candidates derived from observations.
  They are inferences, not findings.
- **Does not establish:** Wrongdoing. Coverage, equipment state and deliberate
  behaviour can each produce the same picture, and SeaCommons does not label a
  gap as deliberate.

### DSC and NAVTEX

- **What they are:** Maritime radio messages. DSC (Digital Selective Calling)
  includes distress alerts. NAVTEX broadcasts navigational and safety warnings.
  SeaCommons handles messages that are already decoded, stores them as Maritime
  Safety evidence and keeps no audio. Only decoded DSC messages with an explicit
  position become map points. Here, SAR means **synthetic aperture radar** when
  it appears in the separate satellite-detection label "Possible dark vessel";
  it does not describe DSC or NAVTEX.
- **Observation or inference:** The decoded message is an observation. A DSC
  distress message can create a candidate that needs human review. A NAVTEX
  message is context only.
- **Do not establish:** A Humanitarian incident. Signal type alone never creates
  one, and several receivers hearing one transmission count as one source.
  Coverage depends on which receivers are configured.

### Derived cue

- **What it is:** An output of a rule or model applied to observations, such as
  an AIS integrity concern, rendezvous context, proximity to infrastructure or a
  bounded radio interpretation. Live shows this as a "derived" verification
  status.
- **Observation or inference:** Inference.
- **Does not establish:** A fact, a motive or illegality. A cue makes an event
  worth investigating and nothing more.

### Corroborated

- **What it is:** Evidence from at least two independent evidence lineages
  supports the same episode or claim.
- **Observation or inference:** Corroboration describes how the evidence relates.
  It is not a new observation.
- **Does not establish:** Certainty, intent, illegality or responsibility.
  Lineages count once: repeated posts of one report, several detectors reading
  the same AIS feed, or several receivers hearing one transmission are not
  independent. A case can show several indicators without being corroborated.

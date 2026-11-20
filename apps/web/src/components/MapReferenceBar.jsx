import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

const PANELS = {
  legend: {
    name: 'Legend',
    heading: 'Map symbols and colors',
    sections: [
      ['▲ Moving vessel', 'Triangle follows a valid AIS heading or course. If the orientation is unknown, the map should not suggest a direction.'],
      ['◆ Unknown direction', 'Diamond: a reported vessel position without a reliable orientation.'],
      ['● Fixed point', 'Location attached to a report or a vessel not reported moving. Refer to the case for its meaning.'],
      ['◉ Concentration', 'Grouped records reflect the number of nearby markers. They do not indicate severity or independently verified events. Zoom in to inspect records.'],
      ['Solid line', 'Successive recorded locations. The connecting line itself is not an independently observed track.'],
      ['Dashed line', 'Missing observations or a modelled route, as explicitly stated in the selected report.'],
      ['Translucent area', 'A modelled search or drift region; not a confirmed sighting.'],
    ],
  },
  guide: {
    name: 'Guide book',
    heading: 'How to explore SeaCommons',
    sections: [
      ['Open a case', 'Select a map symbol or select a case from the left-hand feed. The dossier shows its sources, observations and limits.'],
      ['Search for a vessel', 'Use the name, IMO or MMSI search at the top of the left panel. Results depend on indexed cases, not every vessel worldwide.'],
      ['Change the background', 'Use Map / Satellite in the lower-left corner, beside the feed. Map shows bathymetry; Satellite shows a high-resolution imagery mosaic.'],
      ['Read timestamps', 'LIVE reports the most recent available evidence, not necessarily a current vessel position. PLAY shows historical records at the selected cutoff.'],
      ['Separate evidence from estimates', 'A radio report, AIS fix, forecast, satellite scene and inferred event are different kinds of information.'],
    ],
  },
  methods: {
    name: 'Methods',
    heading: 'Evidence and limitations',
    sections: [
      ['Observed', 'A source recorded a position, message or image. The source and collection time matter.'],
      ['Reported', 'Someone published a claim; corroboration may still be missing.'],
      ['Estimated', 'A calculated trajectory, drift or search area is a model, not an observation.'],
      ['AIS gap', 'No fixes in SeaCommons is a collection gap, not proof that a vessel switched off its transmitter.'],
      ['Bathymetry and imagery', 'Seafloor depth grids are periodically revised. Satellite basemap pixels have different acquisition dates and are not live video.'],
      ['Cluster density', 'Brightness and size indicate a group of observations, not guilt, urgency or confirmation.'],
    ],
  },
};

export default function MapReferenceBar({ context = 'live' }) {
  const [active, setActive] = useState(null);
  useEffect(() => {
    if (!active) return undefined;
    function closeOnEscape(event) { if (event.key === 'Escape') setActive(null); }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [active]);

  const modal = active && (
    <div className="sc-reference-overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) setActive(null);
    }}>
      <section className="sc-reference-dialog" role="dialog" aria-modal="true" aria-label={PANELS[active].heading}>
        <header>
          <div><small>SEACOMMONS / {context.toUpperCase()}</small><h2>{PANELS[active].heading}</h2></div>
          <button type="button" aria-label="Close reference panel" onClick={() => setActive(null)}>×</button>
        </header>
        <div className="sc-reference-dialog__content">
          {PANELS[active].sections.map(([heading, body]) =>
            <section key={heading}><h3>{heading}</h3><p>{body}</p></section>
          )}
        </div>
      </section>
    </div>
  );

  return <>
    <nav className="sc-reference-bar" aria-label="Map reference and documentation">
      {Object.entries(PANELS).map(([key, panel]) =>
        <button key={key} type="button" aria-expanded={active === key}
          onClick={() => setActive((current) => current === key ? null : key)}>{panel.name}</button>
      )}
    </nav>
    {modal && createPortal(modal, document.body)}
  </>;
}

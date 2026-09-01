import React, { useMemo } from 'react';

import { fleetGroups } from '../features/live/sarFleet.js';

const STATUS_LABEL = {
  live: 'LIVE',
  stale: 'STALE',
  offline: 'OFFLINE',
  'unverified-identity': 'ID UNVERIFIED',
};

function FleetGroup({ title, assets, onSelect }) {
  if (!assets.length) return null;
  return (
    <div className="sar-fleet-group">
      <div className="sar-fleet-group-head">
        <span>{title}</span>
        <span>{assets.length}</span>
      </div>
      <ul className="sar-fleet-list">
        {assets.map((a) => (
          <li key={a.mmsi || a.name}>
            <button
              type="button"
              className={`sar-fleet-asset sar-fleet-asset--${a.status}`}
              onClick={() => a.positioned && onSelect?.(a.mmsi)}
              disabled={!a.positioned}
            >
              <strong>{a.name}</strong>
              {a.org && <span className="sar-fleet-org">{a.org}</span>}
              <span className={`sar-fleet-status sar-fleet-status--${a.status}`}>
                {STATUS_LABEL[a.status] || a.status}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * docs/fixes.md F-13 / Phase 4.3: the complete civil + state SAR fleet,
 * grouped and never reduced to only the vessels that happen to have a
 * current AIS fix. An offline vessel stays listed without a map marker.
 */
export default function CivilSarFleetPanel({ fleet, onSelectVessel }) {
  const groups = useMemo(
    () => fleetGroups(fleet?.features || []),
    [fleet],
  );
  const total = groups.civil.length + groups.state.length;
  if (!total) return null;

  return (
    <section className="panel-block sar-fleet-panel">
      <div className="sar-fleet-panel-head">
        <strong>Civil SAR fleet</strong>
        <span>{total} vessels</span>
      </div>
      <FleetGroup title="Civil SAR NGOs" assets={groups.civil} onSelect={onSelectVessel} />
      <FleetGroup title="State SAR authorities" assets={groups.state} onSelect={onSelectVessel} />
    </section>
  );
}

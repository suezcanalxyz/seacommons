import React from 'react';
import { createRoot } from 'react-dom/client';

import '../src/styles.css';
import '../src/ui/ui.css';
import '../src/suez-theme.css';
import MapFloatingPanel from '../src/components/ConePanel.jsx';

const eligible = new URLSearchParams(window.location.search).get('eligible') === '1';
const panel = {
  type: 'radio_receiver',
  feature: {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [15.2, 36.1] },
    properties: {
      receiver_id: 'rx-e2e',
      station_label: 'Mediterranean DSC',
      network_family: 'public',
      country: 'IT',
      state: 'connected',
      active: eligible,
      listen_available: eligible,
      frequency_hz: 2187500,
      mode: 'usb',
      score: 91,
      capabilities_json: JSON.stringify([{ min_hz: 2100000, max_hz: 2200000 }]),
    },
  },
};

createRoot(document.getElementById('root')).render(
  <MapFloatingPanel
    panel={panel}
    onClose={() => {}}
    onComputeDrift={null}
    apiBase={window.location.origin}
    publicMode
    intelDrifts={{ type: 'FeatureCollection', features: [] }}
    loadNearestVessels={async () => []}
    onTriggerIntelDrift={async () => {}}
  />,
);

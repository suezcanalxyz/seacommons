import { useEffect, useState } from 'react';
import { fetchJson } from '../../services/api/client.js';

export function useLiveVesselDossier(apiBase, mmsi) {
  const [result, setResult] = useState(null);
  useEffect(() => {
    if (!mmsi) return undefined;
    let alive = true;
    let timer;
    const refresh = async () => {
      try {
        const data = await fetchJson(apiBase, `/api/v1/live/vessels/${mmsi}/context?hours=168`, { cache: 'no-store' }, 12000);
        if (alive) setResult({ mmsi, data });
      } catch {
        // A transient failure must preserve the last successful observation.
        if (alive) setResult((previous) => previous?.mmsi === mmsi ? previous : { mmsi, data: null });
      } finally {
        if (alive) timer = window.setTimeout(refresh, 60_000);
      }
    };
    refresh();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [apiBase, mmsi]);
  return { data: mmsi && result?.mmsi === mmsi ? result.data : null, loading: Boolean(mmsi && result?.mmsi !== mmsi) };
}

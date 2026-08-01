const STORAGE_KEY = 'seacommons_scenarios_v2';
const MAX_SCENARIOS = 10;

export function storeScenario(scenario) {
  if (typeof window === 'undefined' || scenario?.schema_version !== 'scenario/v2') return;
  try {
    const existing = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]');
    const next = [scenario, ...existing.filter((item) => item.scenario_id !== scenario.scenario_id)]
      .slice(0, MAX_SCENARIOS);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage can be unavailable in private mode. The active scenario still
    // remains in React state and the simulation itself is unaffected.
  }
}

export function loadStoredSimulations() {
  if (typeof window === 'undefined') return [];
  try {
    const scenarios = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]');
    if (!Array.isArray(scenarios)) return [];
    return scenarios
      .filter((scenario) => scenario?.schema_version === 'scenario/v2')
      .slice(0, MAX_SCENARIOS)
      .map((scenario) => ({
        id: scenario.scenario_id,
        label: `${String(scenario.classification?.scenario_type || 'scenario').replace(/_/g, ' ')} @ ${Number(scenario.origin.coordinates[1]).toFixed(3)}, ${Number(scenario.origin.coordinates[0]).toFixed(3)}`,
        ts: scenario.observed_at,
        geojson: scenario.simulation?.products?.drift_geojson || null,
        lat: Number(scenario.origin.coordinates[1]),
        lon: Number(scenario.origin.coordinates[0]),
        params: {
          scenarioType: scenario.classification?.scenario_type,
          vesselType: scenario.subject?.kind,
          persons: scenario.subject?.persons,
          riskLevel: scenario.classification?.risk_level,
        },
        scenario,
      }));
  } catch {
    return [];
  }
}

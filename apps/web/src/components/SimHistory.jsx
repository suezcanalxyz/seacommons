import React from 'react';

export default function SimHistory({ history, activeId, onReplay, onRemove, onClear }) {
  if (!history.length) return null;

  return (
    <section className="panel-block">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <p className="section-kicker" style={{ margin: 0 }}>Session simulations</p>
        <button className="link-button" style={{ fontSize: 10, opacity: 0.45 }} onClick={onClear}>
          Clear all
        </button>
      </div>
      <h3 style={{ marginTop: 0, marginBottom: 8 }}>Simulation history</h3>
      <ul className="sim-history-list">
        {history.map((sim) => {
          const isActive = sim.id === activeId;
          return (
            <li key={sim.id} className={`sim-history-item${isActive ? ' is-active' : ''}`}>
              <div className="sim-history-info">
                <strong title={sim.id}>{sim.label}</strong>
                <span className="sim-history-meta">
                  {new Date(sim.ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                  {sim.params?.persons > 0 ? ` · ${sim.params.persons} pax` : ''}
                </span>
              </div>
              <div className="sim-history-actions">
                <button
                  className={`sim-history-btn${isActive ? ' is-active-sim' : ''}`}
                  onClick={() => onReplay(sim)}
                  title={isActive ? 'Currently shown' : 'Show on map'}
                >
                  {isActive ? '● Live' : '▶ Show'}
                </button>
                {!isActive && (
                  <button
                    className="sim-history-del"
                    onClick={() => onRemove(sim.id)}
                    title="Remove"
                  >×</button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

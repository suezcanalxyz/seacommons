import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth.jsx';
import { fetchJson } from '../services/api/client.js';
import { resolveSiteApiBase } from '../site/liveApi.js';
import {
  accessMatrix,
  guidebook,
  partnerDocuments,
  roadmap,
  seaCommonsProject,
  supportAreas,
  timeline,
  tools,
} from './data.js';

const NAV = ['overview', 'project', 'roadmap', 'documents', 'guidebook', 'tools', 'updates', 'access'];

function formatCount(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return new Intl.NumberFormat('en-GB').format(n);
}

function stateTone(state) {
  const value = String(state || '').toLowerCase();
  if (['live', 'operational', 'available', 'active', 'ongoing', 'manage'].includes(value)) return 'good';
  if (['degraded', 'stabilise', 'prototype', 'active development', 'production + active development'].includes(value)) return 'warn';
  if (['offline', 'blocked', 'disabled'].includes(value)) return 'bad';
  return 'neutral';
}

function StatusPill({ children, state = children }) {
  return <span className={`future-pill future-pill--${stateTone(state)}`}>{children}</span>;
}

function SectionHeader({ eyebrow, title, copy, action }) {
  return (
    <header className="future-section-head">
      <div>
        <span className="future-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {copy ? <p>{copy}</p> : null}
      </div>
      {action || null}
    </header>
  );
}

function useOperationalData() {
  const [snapshot, setSnapshot] = useState({
    status: null,
    counts: null,
    pipeline: null,
    loading: true,
    updatedAt: null,
    error: null,
  });

  const refresh = useCallback(async () => {
    const apiBase = resolveSiteApiBase();
    const requests = await Promise.allSettled([
      fetchJson(apiBase, '/api/v1/status?hours=24', undefined, 9000),
      fetchJson(apiBase, '/api/v1/play/counts', undefined, 9000),
      fetchJson(apiBase, '/api/v1/live/pipeline', undefined, 9000),
    ]);

    const [statusResult, countsResult, pipelineResult] = requests;
    const status = statusResult.status === 'fulfilled' ? statusResult.value : null;
    const counts = countsResult.status === 'fulfilled' ? countsResult.value : null;
    const pipeline = pipelineResult.status === 'fulfilled' ? pipelineResult.value : null;
    const errorCount = requests.filter((result) => result.status === 'rejected').length;

    setSnapshot({
      status,
      counts,
      pipeline,
      loading: false,
      updatedAt: new Date(),
      error: errorCount === requests.length
        ? 'Operational contracts are temporarily unavailable.'
        : errorCount
          ? 'Some operational contracts are unavailable.'
          : null,
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!cancelled) await refresh();
    };
    run();
    const timer = window.setInterval(run, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [refresh]);

  return { ...snapshot, refresh };
}

function WorkstreamList({ project }) {
  return (
    <div className="future-workstreams">
      {project.workstreams.map((stream, index) => (
        <article key={stream.id}>
          <div className="future-workstreams__index">{String(index + 1).padStart(2, '0')}</div>
          <div>
            <div className="future-workstreams__title">
              <h4>{stream.name}</h4>
              <StatusPill state={stream.state}>{stream.state}</StatusPill>
            </div>
            <p>{stream.note}</p>
          </div>
        </article>
      ))}
    </div>
  );
}

function ProjectDetail({ project }) {
  if (!project) return null;
  return (
    <section className="future-project-detail">
      <header>
        <div>
          <span className="future-eyebrow">SeaCommons workspace</span>
          <h2>{project.name}</h2>
        </div>
        <StatusPill state={project.status}>{project.status}</StatusPill>
      </header>

      <p className="future-project-lead">{project.summary}</p>

      <div className="future-detail-grid">
        <div><span>current phase</span><strong>{project.phase}</strong></div>
        <div><span>workstreams</span><strong>{project.workstreams.length}</strong></div>
        <div><span>access</span><strong>full · bootstrap admin</strong></div>
      </div>

      <div className="future-capabilities">
        <span className="future-eyebrow">capabilities / scope</span>
        <div>{project.capabilities.map((item) => <span key={item}>{item}</span>)}</div>
      </div>

      <div className="future-two-col future-two-col--wide">
        <section>
          <span className="future-eyebrow">development workstreams</span>
          <WorkstreamList project={project} />
        </section>
        <section>
          <span className="future-eyebrow">project documents</span>
          <div className="future-doc-list">
            {project.documents.map((doc) => (
              <div className="future-doc-row" key={doc.id}>
                <span>
                  <b>{doc.title}</b>
                  <small>{doc.kind} · {doc.visibility}</small>
                </span>
                <time>{doc.updated}</time>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function OperationalStrip({ ops }) {
  const status = ops.status;
  const counts = ops.counts;
  const pipeline = status?.pipeline || {};
  const serviceState = status?.status || (ops.loading ? 'connecting' : 'unavailable');

  return (
    <section className="future-ops-strip" aria-label="SeaCommons operational status">
      <div>
        <span>system</span>
        <strong>{serviceState}</strong>
        <StatusPill state={serviceState}>{ops.loading ? 'connecting' : serviceState}</StatusPill>
      </div>
      <div>
        <span>public catalogue</span>
        <strong>{formatCount(counts?.total_count)}</strong>
        <small>{formatCount(counts?.humanitarian_count)} humanitarian · {formatCount(counts?.maritime_count)} maritime</small>
      </div>
      <div>
        <span>episodes · 24 h</span>
        <strong>{formatCount(pipeline?.maritime_episodes)}</strong>
        <small>{formatCount(pipeline?.corroborated_episodes)} corroborated</small>
      </div>
      <div>
        <span>investigations · 24 h</span>
        <strong>{formatCount(pipeline?.investigation_hypotheses)}</strong>
        <small>public-safe aggregate</small>
      </div>
    </section>
  );
}

function PipelinePanel({ status }) {
  const pipeline = status?.pipeline || {};
  const sensors = status?.sensor_activity || {};
  const rows = [
    ['raw observations', pipeline.raw_observations],
    ['normalised events', pipeline.parsed_events],
    ['analysis outputs', pipeline.analysis_outputs],
    ['maritime episodes', pipeline.maritime_episodes],
    ['investigation hypotheses', pipeline.investigation_hypotheses],
    ['corroborated episodes', pipeline.corroborated_episodes],
  ];
  const sensorRows = [
    ['AIS fixes', sensors.ais_fixes],
    ['radio bursts', sensors.radio_bursts],
    ['radio events', sensors.radio_events],
    ['satellite observations', sensors.satellite_observations],
  ];

  return (
    <div className="future-metric-panels">
      <section className="future-metric-panel">
        <span className="future-eyebrow">evidence pipeline · 24 h</span>
        <div className="future-metric-list">
          {rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{formatCount(value)}</strong></div>)}
        </div>
      </section>
      <section className="future-metric-panel">
        <span className="future-eyebrow">sensor activity · 24 h</span>
        <div className="future-metric-list">
          {sensorRows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{formatCount(value)}</strong></div>)}
        </div>
      </section>
    </div>
  );
}

function SourceHealth({ pipeline }) {
  const sources = Array.isArray(pipeline?.sources) ? pipeline.sources : [];
  const expected = [
    ['ais', 'AIS'],
    ['first_party', 'First-party'],
    ['partner', 'Partner'],
    ['public_feed', 'Public feeds'],
    ['radio', 'Radio'],
  ];
  const rows = expected.map(([family, label]) => {
    const source = sources.find((item) => item?.family === family);
    return { family, label, state: source?.state || (pipeline ? 'unknown' : 'unavailable'), mode: source?.mode };
  });

  return (
    <section className="future-source-health">
      <span className="future-eyebrow">acquisition families</span>
      <div>
        {rows.map((row) => (
          <article key={row.family}>
            <span>{row.label}</span>
            <div>
              {row.mode ? <small>{row.mode}</small> : null}
              <StatusPill state={row.state}>{row.state}</StatusPill>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function Overview({ ops }) {
  return (
    <>
      <section className="future-hero">
        <span className="future-eyebrow">SeaCommons Futures / partner workspace</span>
        <h1>Project state, development work and operational knowledge.</h1>
        <p>
          A controlled partner workspace for SeaCommons: what exists now, what is being built,
          which materials are current and which SeaCommons operational surfaces are available.
        </p>
        <div className="future-hero__meta">
          <StatusPill state={ops.status?.status || 'unknown'}>{ops.status?.status || 'operational feed pending'}</StatusPill>
          <span>{ops.updatedAt ? `updated ${ops.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'connecting to operational contracts'}</span>
          <button onClick={ops.refresh}>refresh</button>
        </div>
        {ops.error ? <p className="future-inline-note">{ops.error} Static project information remains available.</p> : null}
      </section>

      <OperationalStrip ops={ops} />

      <section className="future-section">
        <SectionHeader
          eyebrow="SeaCommons"
          title="Current development work"
          copy="The workspace is scoped to SeaCommons only. Other Suez products and client projects live on their own surfaces."
        />
        <WorkstreamList project={seaCommonsProject} />
      </section>

      <section className="future-section">
        <SectionHeader
          eyebrow="SeaCommons / live state"
          title="Evidence operations"
          copy="These figures come from the same public-safe contracts used by SeaCommons itself, not a parallel analytics layer."
        />
        <PipelinePanel status={ops.status} />
        <SourceHealth pipeline={ops.pipeline} />
      </section>


    </>
  );
}

function Project() {
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">SeaCommons project</span>
        <h1>One workspace, one project context.</h1>
        <p>
          This Futures domain is the private operational workspace for SeaCommons.
          Other Suez products and client work remain outside this workspace even when they share identity infrastructure.
        </p>
      </section>
      <ProjectDetail project={seaCommonsProject} />
    </>
  );
}

function Roadmap() {
  const lanes = [
    ['now', roadmap.now],
    ['next', roadmap.next],
    ['later', roadmap.later],
  ];

  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">development roadmap</span>
        <h1>What is being built, in what order, and why.</h1>
        <p>
          Roadmap items represent active engineering priorities and planned dependencies.
          They are not promises of completed capability.
        </p>
      </section>

      <section className="future-roadmap-board">
        {lanes.map(([label, items]) => (
          <div className="future-roadmap-lane" key={label}>
            <header><span>{label}</span><strong>{items.length}</strong></header>
            {items.map((item) => (
              <article key={item.project + item.title}>
                <div><small>{item.project}</small><StatusPill state={item.state}>{item.state}</StatusPill></div>
                <h3>{item.title}</h3>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        ))}
      </section>

      <section className="future-section">
        <SectionHeader
          eyebrow="development needs"
          title="Where support compounds"
          copy="Operational needs are shown as project requirements, not as a grant-specific funding template."
        />
        <div className="future-support-grid">
          {supportAreas.map((item) => (
            <article key={item.area}>
              <StatusPill state={item.status}>{item.status}</StatusPill>
              <h3>{item.area}</h3>
              <p>{item.need}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function Documents() {
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">SeaCommons documents</span>
        <h1>Current project materials, without file-name archaeology.</h1>
        <p>
          Documents are scoped to SeaCommons and presented by type, visibility and current source.
          Versioning will move into the final Supabase resource model without changing this workspace boundary.
        </p>
      </section>

      <section className="future-document-table" aria-label="SeaCommons project documents">
        <header>
          <span>document</span><span>project</span><span>type</span><span>access</span><span>updated</span>
        </header>
        {partnerDocuments.map((doc) => (
          <article key={doc.projectId + doc.id}>
            <div><strong>{doc.title}</strong><small>{doc.source}</small></div>
            <span>{doc.project}</span>
            <span>{doc.kind}</span>
            <StatusPill state={doc.visibility === 'restricted' ? 'warn' : 'active'}>{doc.visibility}</StatusPill>
            <time>{doc.updated}</time>
          </article>
        ))}
      </section>
    </>
  );
}

function Guidebook() {
  const [activeId, setActiveId] = useState(guidebook[0].id);
  const active = guidebook.find((item) => item.id === activeId) || guidebook[0];
  const groups = [...new Set(guidebook.map((item) => item.group))];

  return (
    <section className="future-guide">
      <aside>
        <span className="future-eyebrow">guidebook</span>
        {groups.map((group) => (
          <div className="future-guide__group" key={group}>
            <small>{group}</small>
            {guidebook.filter((item) => item.group === group).map((item) => (
              <button key={item.id} className={active.id === item.id ? 'is-active' : ''} onClick={() => setActiveId(item.id)}>
                {item.title}
              </button>
            ))}
          </div>
        ))}
      </aside>
      <article>
        <span className="future-eyebrow">living project knowledge</span>
        <h1>{active.title}</h1>
        <p className="future-guide__summary">{active.summary}</p>
        <hr />
        {active.body.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
        <div className="future-guide__footer">
          <span>native Futures document</span>
          <a href="https://seacommons.org/docs">public docs ↗</a>
        </div>
      </article>
    </section>
  );
}

function Tools() {
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">tools</span>
        <h1>Surfaces you can open from this workspace.</h1>
        <p>
          This page only exposes SeaCommons surfaces. Other Suez products and tools are managed on their own domains
          and are not part of the SeaCommons workspace.
        </p>
      </section>

      <section className="future-tool-grid">
        {tools.map((tool) => {
          const inner = (
            <>
              <div><small>{tool.kind}</small><StatusPill state={tool.state}>{tool.state}</StatusPill></div>
              <h3>{tool.name}</h3>
              <p>{tool.description}</p>
              <span className="future-tool-grid__cta">{tool.href ? 'open ↗' : 'not available yet'}</span>
            </>
          );
          return tool.href
            ? <a key={tool.id} href={tool.href} target="_blank" rel="noreferrer">{inner}</a>
            : <article key={tool.id}>{inner}</article>;
        })}
      </section>
    </>
  );
}

function Updates() {
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">updates</span>
        <h1>A readable development history.</h1>
        <p>Important changes are recorded as project events so partners can understand what changed without reading commit logs.</p>
      </section>
      <section className="future-update-list">
        {timeline.map((item) => (
          <article key={item.date + item.title}>
            <time>{item.date}</time>
            <div>
              <div><span>{item.project}</span><small>{item.kind}</small></div>
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
            </div>
          </article>
        ))}
      </section>
    </>
  );
}

function Access({ user }) {
  const identity = user?.profile?.email || user?.profile?.preferred_username || user?.email || 'authorised administrator';
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">access</span>
        <h1>Full bootstrap access now. Granular grants next.</h1>
        <p>
          The workspace already distinguishes SeaCommons project and resource boundaries. When the final Suez Supabase identity
          tenant is connected, those boundaries become stored membership and access-grant decisions.
        </p>
      </section>

      <section className="future-identity-card">
        <div><span>identity</span><strong>{identity}</strong></div>
        <div><span>role</span><strong>administrator</strong></div>
        <div><span>session</span><strong>full bootstrap access</strong></div>
      </section>

      <section className="future-access-table">
        <header><span>workspace</span><span>level</span><span>scope</span><span>mode</span></header>
        {accessMatrix.map((row) => (
          <article key={row.system}>
            <strong>{row.system}</strong>
            <StatusPill state={row.level}>{row.level}</StatusPill>
            <span>{row.scope}</span>
            <small>{row.state}</small>
          </article>
        ))}
      </section>

      <section className="future-access-note">
        <span className="future-eyebrow">final permission hierarchy</span>
        <p>organisation → SeaCommons workspace → project / subproject → resource or tool</p>
        <p>A grant can stop at any level. Access to one document never implies access to the rest of the project.</p>
      </section>
    </>
  );
}

export default function FuturesApp() {
  const { user, signOut } = useAuth();
  const ops = useOperationalData();
  const [view, setView] = useState('overview');
  return (
    <div className="future-app">
      <aside className="future-sidebar">
        <a className="future-brand" href="https://seacommons.org" aria-label="SeaCommons home">
          <i /><span>SEA<br />COMMONS</span>
        </a>
        <div className="future-product"><span>futures</span><small>partner workspace</small></div>
        <nav aria-label="Futures">
          {NAV.map((item) => (
            <button key={item} className={view === item ? 'is-active' : ''} onClick={() => setView(item)}>
              <span>{item}</span><i>↗</i>
            </button>
          ))}
        </nav>
        <div className="future-sidebar__base">
          <span>full access</span>
          <button onClick={() => signOut?.()}>sign out</button>
        </div>
      </aside>

      <main className="future-main">
        <header className="future-topbar">
          <div><span>SeaCommons / Futures</span><b>{view}</b></div>
          <div className="future-topbar__links">
            <a href="https://live.seacommons.org">live ↗</a>
            <a href="https://seacommons.org">public site ↗</a>
          </div>
        </header>

        <div className="future-content">
          {view === 'overview' && <Overview ops={ops} />}
          {view === 'project' && <Project />}
          {view === 'roadmap' && <Roadmap />}
          {view === 'documents' && <Documents />}
          {view === 'guidebook' && <Guidebook />}
          {view === 'tools' && <Tools />}
          {view === 'updates' && <Updates />}
          {view === 'access' && <Access user={user} />}
        </div>
      </main>
    </div>
  );
}

import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth.jsx';
import { allProjects, clientProjects, guidebook, proprietaryProjects, timeline } from './data.js';

const NAV = ['overview', 'projects', 'timeline', 'budget', 'guidebook', 'access'];

function ProjectCard({ project, active, onOpen }) {
  return (
    <button className={`future-project-card ${active ? 'is-active' : ''}`} onClick={() => onOpen(project.id)}>
      <div className="future-project-card__top">
        <span>{project.type === 'proprietary' ? 'proprietary system' : 'client project'}</span>
        <i>{project.status}</i>
      </div>
      <h3>{project.name}</h3>
      <p>{project.summary}</p>
      <div className="future-progress" aria-label={`${project.progress}% complete`}>
        <i style={{ width: `${project.progress}%` }} />
      </div>
      <div className="future-project-card__meta">
        <span>{project.phase}</span>
        <strong>{project.progress}%</strong>
      </div>
    </button>
  );
}

function ProjectDetail({ project }) {
  if (!project) return null;
  return (
    <section className="future-project-detail">
      <header>
        <div>
          <span className="future-eyebrow">{project.type === 'proprietary' ? 'proprietary system' : 'client project'}</span>
          <h2>{project.name}</h2>
        </div>
        <span className="future-status">{project.status}</span>
      </header>
      <p className="future-project-lead">{project.summary}</p>
      <div className="future-detail-grid">
        <div>
          <span>current phase</span>
          <strong>{project.phase}</strong>
        </div>
        <div>
          <span>progress</span>
          <strong>{project.progress}%</strong>
        </div>
        <div>
          <span>access</span>
          <strong>full · bootstrap</strong>
        </div>
      </div>
      <div className="future-two-col">
        <section>
          <span className="future-eyebrow">roadmap</span>
          <ol className="future-roadmap">
            {project.roadmap.map((item, index) => <li key={item}><b>{String(index + 1).padStart(2, '0')}</b><span>{item}</span></li>)}
          </ol>
        </section>
        <section>
          <span className="future-eyebrow">documents</span>
          <div className="future-doc-list">
            {project.documents.map((doc) => (
              <button key={doc.title}>
                <span><b>{doc.title}</b><small>{doc.kind}</small></span>
                <time>{doc.updated}</time>
              </button>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function Overview({ live }) {
  return (
    <>
      <section className="future-hero">
        <span className="future-eyebrow">SeaCommons Futures</span>
        <h1>Projects, roadmaps and shared infrastructure.</h1>
        <p>A controlled workspace for proprietary systems, selected client projects, documents and future tools.</p>
      </section>

      <section className="future-kpis">
        <div><span>proprietary systems</span><strong>{proprietaryProjects.length}</strong></div>
        <div><span>client projects</span><strong>{clientProjects.length}</strong></div>
        <div><span>live evidence</span><strong>{live.count ?? '—'}</strong><small>{live.label}</small></div>
        <div><span>access mode</span><strong>full</strong><small>bootstrap admin</small></div>
      </section>

      <section className="future-section">
        <header><span className="future-eyebrow">proprietary</span><h2>Systems</h2></header>
        <div className="future-card-grid">
          {proprietaryProjects.map((project) => <ProjectCard key={project.id} project={project} onOpen={() => {}} />)}
        </div>
      </section>

      <section className="future-section">
        <header><span className="future-eyebrow">commercial</span><h2>Client projects</h2></header>
        <div className="future-card-grid">
          {clientProjects.map((project) => <ProjectCard key={project.id} project={project} onOpen={() => {}} />)}
        </div>
      </section>
    </>
  );
}

function Projects({ selectedId, onSelect }) {
  const selected = allProjects.find((project) => project.id === selectedId) || proprietaryProjects[0];
  return (
    <>
      <section className="future-page-head">
        <span className="future-eyebrow">projects</span>
        <h1>Access by relationship, not by portal.</h1>
        <p>Proprietary systems and client work stay structurally distinct while sharing one permission layer.</p>
      </section>
      <div className="future-project-groups">
        <section>
          <h2>Proprietary systems</h2>
          <div className="future-card-grid future-card-grid--compact">
            {proprietaryProjects.map((project) => <ProjectCard key={project.id} project={project} active={project.id === selected.id} onOpen={onSelect} />)}
          </div>
        </section>
        <section>
          <h2>Client projects</h2>
          <div className="future-card-grid future-card-grid--compact">
            {clientProjects.map((project) => <ProjectCard key={project.id} project={project} active={project.id === selected.id} onOpen={onSelect} />)}
          </div>
        </section>
      </div>
      <ProjectDetail project={selected} />
    </>
  );
}

function Timeline() {
  return (
    <section className="future-page-head">
      <span className="future-eyebrow">timeline</span>
      <h1>Development history.</h1>
      <div className="future-timeline">
        {timeline.map(([date, project, item]) => <div key={date + item}><time>{date}</time><b>{project}</b><p>{item}</p></div>)}
      </div>
    </section>
  );
}

function Budget() {
  return (
    <section className="future-page-head">
      <span className="future-eyebrow">budget</span>
      <h1>Project economics, with visibility by access grant.</h1>
      <p>Financial data will be permissioned per project. The bootstrap view is intentionally structural until the shared data layer is connected.</p>
      <div className="future-empty-grid">
        <div><span>planned</span><strong>connect data source</strong></div>
        <div><span>committed</span><strong>connect data source</strong></div>
        <div><span>spent</span><strong>connect data source</strong></div>
      </div>
    </section>
  );
}

function Guidebook() {
  const [active, setActive] = useState(guidebook[0][1]);
  return (
    <section className="future-guide">
      <aside>
        <span className="future-eyebrow">guidebook</span>
        {guidebook.map(([group, title]) => (
          <button key={group + title} className={active === title ? 'is-active' : ''} onClick={() => setActive(title)}>
            <small>{group}</small><span>{title}</span>
          </button>
        ))}
      </aside>
      <article>
        <span className="future-eyebrow">living document</span>
        <h1>{active}</h1>
        <p>This page is ready to become a native, readable document surface. Content will live here rather than being reduced to downloadable PDFs, with decks and files attached as resources.</p>
        <hr />
        <h2>Structure</h2>
        <p>Overview, current state, decisions, roadmap, related documents and references can be composed into the same reading surface.</p>
      </article>
    </section>
  );
}

function Access({ user }) {
  return (
    <section className="future-page-head">
      <span className="future-eyebrow">access</span>
      <h1>Bootstrap permission layer.</h1>
      <p>For this first implementation every authenticated administrator receives full access. The next step replaces this bootstrap grant with organization, project, subproject and resource-level grants.</p>
      <div className="future-access-card">
        <div><span>signed in as</span><strong>{user?.profile?.email || user?.profile?.preferred_username || 'authorised user'}</strong></div>
        <div><span>current role</span><strong>administrator</strong></div>
        <div><span>systems</span><strong>all proprietary + client projects</strong></div>
      </div>
    </section>
  );
}

export default function FuturesApp() {
  const { user, signOut } = useAuth();
  const [view, setView] = useState('overview');
  const [selectedProject, setSelectedProject] = useState('seacommons');
  const [live, setLive] = useState({ count: null, label: 'connecting' });

  useEffect(() => {
    let alive = true;
    fetch('/api/v1/live/signals?limit=100&days=2')
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('offline')))
      .then((data) => {
        if (!alive) return;
        const count = Array.isArray(data?.features) ? data.features.length : Number(data?.count ?? 0);
        setLive({ count: Number.isFinite(count) ? count : null, label: 'public signals · 48h' });
      })
      .catch(() => alive && setLive({ count: null, label: 'ops feed unavailable' }));
    return () => { alive = false; };
  }, []);

  const title = useMemo(() => view === 'projects' ? 'projects' : view, [view]);

  return (
    <div className="future-app">
      <aside className="future-sidebar">
        <a className="future-brand" href="https://seacommons.org" aria-label="SeaCommons home">
          <i /><span>SEA<br />COMMONS</span>
        </a>
        <div className="future-product"><span>futures</span><small>private workspace</small></div>
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
          <div><span>SeaCommons / Futures</span><b>{title}</b></div>
          <a href="https://seacommons.org">public site ↗</a>
        </header>
        <div className="future-content">
          {view === 'overview' && <Overview live={live} />}
          {view === 'projects' && <Projects selectedId={selectedProject} onSelect={setSelectedProject} />}
          {view === 'timeline' && <Timeline />}
          {view === 'budget' && <Budget />}
          {view === 'guidebook' && <Guidebook />}
          {view === 'access' && <Access user={user} />}
        </div>
      </main>
    </div>
  );
}

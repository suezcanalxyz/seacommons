import React, { useEffect, useState } from 'react';

export default function JobMonitor({ apiBase, fetchJson }) {
  const [jobs, setJobs] = useState([]); const [workers, setWorkers] = useState([]); const [error, setError] = useState('');
  async function refresh() {
    try {
      const [j, w] = await Promise.all([fetchJson(apiBase, '/api/v1/jobs?limit=30'), fetchJson(apiBase, '/api/v1/admin/workers')]);
      setJobs(j); setWorkers(w); setError('');
    } catch (err) { setError(err.message || 'Job monitor unavailable'); }
  }
  useEffect(() => { refresh(); const timer = setInterval(refresh, 15000); return () => clearInterval(timer); }, [apiBase]);
  async function retry(id) { await fetchJson(apiBase, `/api/v1/jobs/${id}/retry`, { method: 'POST' }); refresh(); }
  const counts = jobs.reduce((out, job) => ({ ...out, [job.status]: (out[job.status] || 0) + 1 }), {});
  return <section className="panel-block job-monitor"><div className="panel-title-row"><div><p className="section-kicker">Durable queue</p><h3>Jobs & workers</h3></div><button onClick={refresh}>Refresh</button></div>
    {error && <div className="demo-note">{error}</div>}
    <div className="job-counters">{['queued','running','retry','dead'].map(s => <span key={s}><b>{counts[s] || 0}</b>{s}</span>)}</div>
    <ul className="worker-list">{workers.map(worker => <li key={worker.worker_id}><i className={worker.alive ? 'alive' : ''}/><span><strong>{worker.hostname}</strong><small>{worker.current_job_id ? `job ${worker.current_job_id.slice(0,8)}` : 'idle'}</small></span></li>)}</ul>
    <ul className="job-list">{jobs.slice(0,15).map(job => <li key={job.job_id}><span><strong>{job.job_type}</strong><small>{job.job_id.slice(0,8)} · attempt {job.attempts}/{job.max_attempts}</small></span><b className={`job-status ${job.status}`}>{job.status}</b>{['dead','retry'].includes(job.status) && <button onClick={() => retry(job.job_id)}>Retry</button>}</li>)}</ul>
  </section>;
}

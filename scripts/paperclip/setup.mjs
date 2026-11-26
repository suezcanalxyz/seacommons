import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const base = 'http://127.0.0.1:3100/api';
const cwd = dirname(fileURLToPath(import.meta.url));

async function api(path, body) {
  const response = await fetch(base + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`);
  return response.json();
}

const companyName = 'SeaCommons QA';
const company = (await api('/companies')).find(({ name }) => name === companyName)
  ?? await api('/companies', { name: companyName, description: 'Read-only QA of public maritime position reporting.' });
const scope = `/companies/${company.id}`;
const agentName = 'LIVE AIS public API check';
const agent = (await api(`${scope}/agents`)).find(({ name }) => name === agentName)
  ?? await api(`${scope}/agents`, {
    name: agentName, adapterType: 'process',
    adapterConfig: { command: process.execPath, args: ['check-live-ais.mjs'], cwd, timeoutSec: 65 },
    runtimeConfig: { heartbeat: { enabled: false } },
  });
const routineTitle = 'Check SeaCommons LIVE AIS';
const routine = (await api(`${scope}/routines`)).find(({ title }) => title === routineTitle)
  ?? await api(`${scope}/routines`, {
    title: routineTitle, assigneeAgentId: agent.id,
    description: 'Read public LIVE cases and report the timestamps returned by the public AIS dossier API.',
  });

console.log(JSON.stringify({ company: company.id, agent: agent.id, routine: routine.id }));
if (process.argv.includes('--run')) {
  const run = await api(`/routines/${routine.id}/run`, {});
  console.log(JSON.stringify({ run: run.id, status: run.status }));
}

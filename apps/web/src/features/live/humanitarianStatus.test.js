import test from 'node:test';
import assert from 'node:assert/strict';

import {
  humanitarianOperationalStatus,
  humanitarianSourceReportedStatus,
} from './humanitarianStatus.js';

test('a later canonical review takes precedence over an earlier ongoing source post', () => {
  const props = {
    incident_status: 'needs_review',
    incident_lifecycle: 'needs_review',
    humanitarian_status: 'ongoing',
    resolved_at: '2026-11-01T10:00:00Z',
  };
  assert.equal(humanitarianOperationalStatus(props), 'needs review');
  assert.equal(humanitarianSourceReportedStatus(props), 'ongoing');
  // A historical resolution timestamp is retained as evidence, not used as current status.
  assert.equal(props.resolved_at, '2026-11-01T10:00:00Z');
});

test('canonical outcome unknown cannot be presented as ongoing distress', () => {
  assert.equal(humanitarianOperationalStatus({
    incident_status: 'outcome_unknown',
    humanitarian_status: 'ongoing',
  }), 'outcome unknown');
});

test('canonical resolved status supersedes an earlier source post', () => {
  assert.equal(humanitarianOperationalStatus({
    incident_status: 'resolved',
    humanitarian_status: 'ongoing',
  }), 'resolved');
});

test('legacy events without canonical incident status fall back to lifecycle', () => {
  assert.equal(humanitarianOperationalStatus({ incident_lifecycle: 'needs_review' }), 'needs review');
  assert.equal(humanitarianOperationalStatus({}, 'archived'), 'outcome unknown');
  assert.equal(humanitarianOperationalStatus({}), 'Not established');
});

test('unknown canonical status never overrides a known lifecycle', () => {
  assert.equal(humanitarianOperationalStatus({
    incident_status: 'not_a_status',
    incident_lifecycle: 'active',
  }), 'active');
});

test('missing source-reported status is not fabricated', () => {
  assert.equal(humanitarianSourceReportedStatus({}), null);
});

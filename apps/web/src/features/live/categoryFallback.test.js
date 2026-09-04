// docs/fixes.md M10 map design rule: "unknown/unclassified does not
// silently appear as 'Other'" -- meaning an unmatched type must fail
// closed into the real, explicit Unclassified bucket (not a legitimate-
// looking category), and that bucket must never silently render as if it
// were a normal visible layer. categoryOf/categoryColor/descriptionOf/
// categoryColorExpression/INTEL_MAP_CATEGORIES had no direct test
// coverage before this file.
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  categoryColor,
  categoryColorExpression,
  categoryOf,
  descriptionOf,
  INTEL_MAP_CATEGORIES,
  SIGNAL_CATEGORIES,
} from '../intel/categories.js';

test('an unrecognised type fails closed to the explicit Unclassified bucket', () => {
  assert.equal(categoryOf('not_a_real_event_type'), 'other');
  assert.equal(categoryOf(undefined), 'other');
  assert.equal(categoryOf(''), 'other');
});

test('a known type never falls back to Unclassified', () => {
  assert.equal(categoryOf('distress'), 'distress');
  assert.equal(categoryOf('ais_spike'), 'ais');
  assert.equal(categoryOf('gdacs'), 'hazard');
});

test('categoryColor falls back to the Unclassified colour for an unknown key', () => {
  const other = SIGNAL_CATEGORIES.find((c) => c.key === 'other');
  assert.equal(categoryColor('not_a_real_category'), other.color);
});

test('descriptionOf never returns undefined for an unknown type', () => {
  const description = descriptionOf('not_a_real_event_type');
  assert.equal(typeof description, 'string');
  assert.ok(description.length > 0);
});

test('the Unclassified bucket is excluded from the toggleable map layers', () => {
  // docs/fixes.md M10: unclassified must never silently render as if it
  // were a normal visible layer -- it has no dedicated map toggle.
  assert.ok(!INTEL_MAP_CATEGORIES.some((c) => c.key === 'other'));
});

test('categoryColorExpression always ends with an explicit fallback colour', () => {
  // MapLibre `match` expressions require a trailing default; without one,
  // an unmatched feature type would render undefined/invisible rather
  // than failing closed to a visible Unclassified colour.
  const expr = categoryColorExpression();
  const other = SIGNAL_CATEGORIES.find((c) => c.key === 'other');
  assert.equal(expr[0], 'match');
  assert.equal(expr.at(-1), other.color);
});

test('every category the colour expression can match resolves to a distinct or intentionally shared colour, never undefined', () => {
  const expr = categoryColorExpression();
  // Every entry after the initial ['match', ['get','type']] pair is
  // (matchValue, colour) — colour must always be a real hex string.
  for (let i = 2; i < expr.length - 1; i += 2) {
    assert.match(expr[i + 1], /^#[0-9a-f]{6}$/i);
  }
});

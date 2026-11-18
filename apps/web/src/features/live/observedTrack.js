import { reconstructAisGaps } from '../play/aisGapGeometry.js';

export function splitObservedTrackSegments(points = [], maxJumpKm = 80) {
  return reconstructAisGaps([{ track_points: points }], { maxJumpKm }).segments;
}

// A visual reference only. Never scrape, parse or automate the VesselFinder widget.
export function validIMO(value) {
  return /^\d{7}$/.test(String(value || '').trim());
}

export function validMMSI(value) {
  return /^\d{9}$/.test(String(value || '').trim());
}

export function vesselFinderEmbedHtml({ imo = '', mmsi = '' }) {
  const safeIMO = validIMO(imo) ? String(imo).trim() : '';
  const safeMMSI = validMMSI(mmsi) ? String(mmsi).trim() : '';
  if (!safeIMO && !safeMMSI) throw new Error('A valid IMO or MMSI is required.');
  const identity = safeIMO ? 'var imo=' + JSON.stringify(safeIMO) + ';' : 'var mmsi=' + JSON.stringify(safeMMSI) + ';';
  return [
    '<!doctype html><html lang="en"><head><meta charset="utf-8">',
    '<meta name="referrer" content="no-referrer">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<style>html,body{margin:0;width:100%;height:100%;background:#091523;color:#fff}body{min-height:400px}</style>',
    '</head><body>',
    '<script>var width="100%";var height="460";var names=true;var show_track=true;',
    identity, '</script>',
    '<script src="https://www.vesselfinder.com/aismap.js"></script>',
    '</body></html>',
  ].join('');
}

/** A human-operated fallback, not a programmatic AIS feed. */
export function vesselFinderPageUrl({imo='',mmsi=''}) {
  const safeIMO=validIMO(imo) ? String(imo).trim() : '';
  const safeMMSI=validMMSI(mmsi) ? String(mmsi).trim() : '';
  if (!safeIMO && !safeMMSI) return '';
  // VesselFinder's public vessel detail URL is keyed by IMO. Its MMSI-only
  // search is left to the provider: never fabricate a deep link for that ID.
  return safeIMO ? 'https://www.vesselfinder.com/vessels/details/'+safeIMO
    : 'https://www.vesselfinder.com/vessels';
}

export function isolatedVesselFinderFrameUrl(identity) {
  // A data: frame has an opaque origin. Combined with the sandbox below,
  // this permits the official widget to use its browser APIs without granting
  // the third-party script access to the authenticated Futures origin.
  return 'data:text/html;charset=utf-8,'+encodeURIComponent(vesselFinderEmbedHtml(identity));
}

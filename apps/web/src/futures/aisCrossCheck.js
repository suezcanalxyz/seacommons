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

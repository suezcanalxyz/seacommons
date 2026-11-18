// Draw the fixed endpoint labels locally so they work without a glyph server.
export function addMovementLabels(map, id, source) {
  const labels = ['Last observed fix', 'Published gap position', 'Next recorded AIS fix',
    'Next recorded fix', 'Last AIS fix', 'Next AIS fix', 'Model start', 'Model endpoint'];
  for (const label of labels) {
    const canvas = document.createElement('canvas');
    canvas.width = 208;
    canvas.height = 38;
    const ctx = canvas.getContext('2d');
    if (!ctx) continue;
    ctx.font = 'bold 20px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const width = Math.ceil(ctx.measureText(label).width) + 14;
    ctx.fillStyle = '#07141a';
    ctx.fillRect((canvas.width - width) / 2, 0, width, 37);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(label, canvas.width / 2, 19);
    map.addImage(label, ctx.getImageData(0, 0, canvas.width, canvas.height), { pixelRatio: 2 });
  }
  map.addLayer({ id, type: 'symbol', source, filter: ['has', 'label'],
    layout: { 'icon-image': ['get', 'label'], 'icon-anchor': 'bottom', 'icon-offset': [0, -10], 'icon-allow-overlap': true } });
}

const ANTENNA_PATH = 'M32 28v20m-9 0h18M24 14a13 13 0 0 0 0 21m16-21a13 13 0 0 1 0 21M18 8a21 21 0 0 0 0 33M46 8a21 21 0 0 1 0 33';

function antennaColor(receiving) {
  return receiving ? '#c4a5ff' : '#ffffff';
}

export function radioStationIconMarkup(receiving) {
  return `<svg viewBox="0 0 64 64" width="32" height="32" aria-hidden="true">
    <path d="${ANTENNA_PATH}" fill="none" stroke="#080910" stroke-width="9" stroke-linecap="round"/>
    <path d="${ANTENNA_PATH}" fill="none" stroke="${antennaColor(receiving)}" stroke-width="4" stroke-linecap="round"/>
    <circle cx="32" cy="24" r="5" fill="${antennaColor(receiving)}" stroke="#080910" stroke-width="2"/>
  </svg>`;
}

export function installRadioStationIcon(map, receiving) {
  const name = receiving ? 'seacommons-radio-antenna-active' : 'seacommons-radio-antenna-offline';
  if (map.hasImage(name)) return name;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const antenna = new Path2D(ANTENNA_PATH);
  ctx.lineCap = 'round';
  ctx.strokeStyle = '#080910';
  ctx.lineWidth = 9;
  ctx.stroke(antenna);
  ctx.strokeStyle = ctx.fillStyle = antennaColor(receiving);
  ctx.lineWidth = 4;
  ctx.stroke(antenna);
  ctx.beginPath();
  ctx.arc(32, 24, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#080910';
  ctx.lineWidth = 2;
  ctx.stroke();
  map.addImage(name, ctx.getImageData(0, 0, 64, 64), { pixelRatio: 2 });
  return name;
}

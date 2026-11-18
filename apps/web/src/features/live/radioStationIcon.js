/** Register a native MapLibre antenna image for verified active RF receivers.
 * Keeps the signal-source icon distinct from vessel, incident and NAVTEX markers.
 * Uses a small local canvas: no external icon service, font, or third-party asset.
 */
export function installActiveRadioStationIcon(map) {
  const name = 'seacommons-radio-antenna-active';
  if (map.hasImage(name)) return name;
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 64;
  const c = canvas.getContext('2d');
  if (!c) return null;
  c.fillStyle = '#07151b';
  c.strokeStyle = '#a78bfa';
  c.lineWidth = 4;
  c.beginPath(); c.arc(32, 32, 28, 0, Math.PI * 2); c.fill(); c.stroke();
  c.strokeStyle = '#ffffff';
  c.lineWidth = 3.5;
  c.lineCap = 'round';
  // An antenna mast and symmetric transmitting waves, visibly not a vessel icon.
  c.beginPath(); c.moveTo(32, 27); c.lineTo(32, 46); c.moveTo(23, 46); c.lineTo(41, 46); c.stroke();
  c.fillStyle = '#ffffff'; c.beginPath(); c.arc(32, 24, 3.4, 0, Math.PI * 2); c.fill();
  c.beginPath(); c.arc(32, 24, 11, -2.42, -0.72); c.stroke();
  c.beginPath(); c.arc(32, 24, 11, 3.86, 5.56); c.stroke();
  c.beginPath(); c.arc(32, 24, 19, -2.42, -0.72); c.stroke();
  c.beginPath(); c.arc(32, 24, 19, 3.86, 5.56); c.stroke();
  const pixels = c.getImageData(0, 0, 64, 64);
  map.addImage(name, { width: 64, height: 64, data: pixels.data }, { pixelRatio: 2 });
  return name;
}

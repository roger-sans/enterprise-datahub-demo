export function lineChart(canvas, points, options) {
  if (!canvas || points.length === 0) return;
  const ctx = canvas.getContext('2d');
  const bounds = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = bounds.width;
  const height = bounds.height;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.scale(dpr, dpr);
  const left = 43, right = width - 13, top = 9, bottom = height - 24;
  const values = points.map(point => point.value);
  const min = options.percent ? 70 : 0;
  const max = options.percent ? 100 : Math.max(1, Math.ceil(Math.max(...values) / 4) * 4);
  const target = options.percent ? 95 : null;
  const x = i => left + i * (right - left) / Math.max(1, values.length - 1);
  const y = value => bottom - (value - min) * (bottom - top) / (max - min);
  ctx.font = '10px system-ui';
  for (let index = 0; index <= 4; index++) {
    const value = min + (max - min) * index / 4;
    const label = options.percent ? Math.round(value) + '%' : Intl.NumberFormat('en', { notation: 'compact' }).format(value);
    ctx.fillStyle = '#657681';
    ctx.fillText(label, 2, y(value) + 3);
    ctx.strokeStyle = '#e7ecef';
    ctx.beginPath();
    ctx.moveTo(left, y(value));
    ctx.lineTo(right, y(value));
    ctx.stroke();
  }
  const step = Math.max(1, Math.ceil(points.length / (width < 370 ? 4 : 6)));
  points.forEach((point, i) => {
    if (i % step) return;
    const position = Math.min(right - 14, Math.max(left - 4, x(i) - 9));
    ctx.fillStyle = '#657681';
    ctx.fillText(new Date(point.period + 'T00:00:00Z').toLocaleDateString('en-GB', {
      day: 'numeric', month: 'short', timeZone: 'UTC',
    }), position, height - 4);
  });
  const gradient = ctx.createLinearGradient(0, top, 0, bottom);
  gradient.addColorStop(0, '#44bd9960');
  gradient.addColorStop(1, '#44bd9907');
  ctx.beginPath();
  values.forEach((value, i) => i ? ctx.lineTo(x(i), y(value)) : ctx.moveTo(x(0), y(value)));
  ctx.lineTo(x(values.length - 1), bottom);
  ctx.lineTo(left, bottom);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();
  if (target !== null) {
    ctx.setLineDash([4, 5]);
    ctx.strokeStyle = '#819797';
    ctx.beginPath();
    ctx.moveTo(left, y(target));
    ctx.lineTo(right, y(target));
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.beginPath();
  values.forEach((value, i) => i ? ctx.lineTo(x(i), y(value)) : ctx.moveTo(x(0), y(value)));
  ctx.lineWidth = 2.4;
  ctx.strokeStyle = '#128269';
  ctx.stroke();
  for (const [i, value] of values.entries()) {
    ctx.beginPath();
    ctx.arc(x(i), y(value), i === values.length - 1 ? 3.5 : 2.3, 0, Math.PI * 2);
    ctx.fillStyle = '#128269';
    ctx.fill();
  }
  canvas.onpointermove = event => {
    const index = Math.max(0, Math.min(points.length - 1,
      Math.round((event.clientX - bounds.left - left) * (points.length - 1) / Math.max(1, right - left))));
    canvas.title = points[index].period + ' · ' + points[index].value + (options.percent ? '%' : '');
  };
}

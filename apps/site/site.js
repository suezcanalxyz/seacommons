(() => {
  const menuButton = document.querySelector('[data-menu-toggle]');
  const nav = document.querySelector('[data-nav]');

  const closeMenu = () => {
    if (!menuButton || !nav) return;
    menuButton.setAttribute('aria-expanded', 'false');
    nav.classList.remove('is-open');
    document.body.classList.remove('menu-open');
  };

  menuButton?.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') !== 'true';
    menuButton.setAttribute('aria-expanded', String(open));
    nav.classList.toggle('is-open', open);
    document.body.classList.toggle('menu-open', open);
  });
  nav?.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
  window.addEventListener('resize', () => {
    if (window.innerWidth > 760) closeMenu();
  });

  const utc = document.querySelector('[data-utc]');
  const updateClock = () => {
    if (!utc) return;
    utc.textContent = `UTC ${new Date().toISOString().slice(11, 19)}`;
  };
  updateClock();
  window.setInterval(updateClock, 1000);

  const reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: .08 });
    reveals.forEach((element) => observer.observe(element));
  } else {
    reveals.forEach((element) => element.classList.add('is-visible'));
  }

  const statusLight = document.querySelector('[data-demo-light]');
  const statusState = document.querySelector('[data-demo-state]');
  const statusDetail = document.querySelector('[data-demo-detail]');
  const statusController = new AbortController();
  const statusTimer = window.setTimeout(() => statusController.abort(), 4500);
  fetch('/health', { signal: statusController.signal })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('unavailable')))
    .then((health) => {
      if (health?.status !== 'ok') return;
      statusLight?.classList.add('online');
      if (statusState) statusState.textContent = 'Demo online';
      if (statusDetail) statusDetail.textContent = 'Synthetic and bounded scenarios';
    })
    .catch(() => {
      if (statusState) statusState.textContent = 'Demo surface';
      if (statusDetail) statusDetail.textContent = 'Check Play for current availability';
    })
    .finally(() => window.clearTimeout(statusTimer));

  const canvas = document.querySelector('[data-signal-canvas]');
  if (!(canvas instanceof HTMLCanvasElement)) return;
  const context = canvas.getContext('2d');
  if (!context) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let width = 0;
  let height = 0;
  let frame = 0;
  let animationId = 0;
  const traces = [
    { y: .36, phase: 0, speed: .0021, color: '202,255,61', amplitude: .11 },
    { y: .53, phase: 1.8, speed: .0015, color: '255,96,60', amplitude: .075 },
    { y: .68, phase: 3.4, speed: .0012, color: '80,118,255', amplitude: .12 },
  ];

  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const bounds = canvas.getBoundingClientRect();
    width = Math.max(1, bounds.width);
    height = Math.max(1, bounds.height);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  };

  const pointFor = (trace, x, time) => {
    const primary = Math.sin(x * 7.2 + trace.phase + time * trace.speed);
    const secondary = Math.cos(x * 16.5 - trace.phase + time * trace.speed * .63);
    return height * (trace.y + trace.amplitude * primary * .62 + trace.amplitude * secondary * .22);
  };

  const draw = (time = 0) => {
    context.clearRect(0, 0, width, height);
    context.save();
    context.globalCompositeOperation = 'screen';

    traces.forEach((trace, traceIndex) => {
      context.beginPath();
      for (let step = 0; step <= 90; step += 1) {
        const normalized = step / 90;
        const x = -width * .04 + normalized * width * 1.08;
        const y = pointFor(trace, normalized, time);
        if (step === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.strokeStyle = `rgba(${trace.color},${traceIndex === 0 ? .44 : .27})`;
      context.lineWidth = traceIndex === 0 ? 1.6 : 1;
      context.stroke();

      const progress = ((time * trace.speed * .055 + trace.phase * .13) % 1 + 1) % 1;
      const markerX = progress * width;
      const markerY = pointFor(trace, progress, time);
      context.beginPath();
      context.arc(markerX, markerY, traceIndex === 0 ? 4 : 3, 0, Math.PI * 2);
      context.fillStyle = `rgba(${trace.color},.95)`;
      context.fill();
      context.beginPath();
      context.arc(markerX, markerY, 14 + traceIndex * 4, 0, Math.PI * 2);
      context.strokeStyle = `rgba(${trace.color},.18)`;
      context.stroke();
    });

    const originX = width * .32;
    const originY = height * .57;
    for (let ring = 1; ring <= 4; ring += 1) {
      context.beginPath();
      context.ellipse(originX, originY, ring * width * .065, ring * height * .035, -.28, 0, Math.PI * 2);
      context.strokeStyle = `rgba(202,255,61,${.12 - ring * .018})`;
      context.setLineDash([4, 7]);
      context.stroke();
    }
    context.setLineDash([]);
    context.restore();

    frame += 1;
    if (!reducedMotion) animationId = window.requestAnimationFrame(draw);
  };

  resize();
  draw(0);
  if (!reducedMotion) animationId = window.requestAnimationFrame(draw);
  window.addEventListener('resize', resize);
  window.addEventListener('pagehide', () => window.cancelAnimationFrame(animationId));
})();

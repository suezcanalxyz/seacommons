(() => {
  const utc = document.querySelector("[data-utc]");
  const updateClock = () => {
    if (utc) utc.textContent = `UTC ${new Date().toISOString().slice(11, 19)}`;
  };
  updateClock();
  window.setInterval(updateClock, 1000);

  const menuToggle = document.querySelector("[data-menu-toggle]");
  const nav = document.querySelector("[data-nav]");
  if (menuToggle && nav) {
    menuToggle.addEventListener("click", () => {
      const open = nav.getAttribute("data-open") === "true";
      nav.setAttribute("data-open", String(!open));
      menuToggle.setAttribute("aria-expanded", String(!open));
    });
    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        nav.setAttribute("data-open", "false");
        menuToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const canvas = document.querySelector("[data-signal-canvas]");
  if (!(canvas instanceof HTMLCanvasElement) || reducedMotion) return;

  const context = canvas.getContext("2d");
  if (!context) return;

  const signals = [
    { y: .3, amplitude: .07, frequency: 5.2, speed: .00014, phase: .2, color: "215,255,69", alpha: .22 },
    { y: .55, amplitude: .09, frequency: 4.1, speed: .0001, phase: 2.1, color: "47,107,255", alpha: .24 },
    { y: .78, amplitude: .05, frequency: 6.8, speed: .00008, phase: 4.5, color: "241,244,233", alpha: .1 },
  ];

  let width = 0;
  let height = 0;
  let animationId = 0;

  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const bounds = canvas.getBoundingClientRect();
    width = Math.max(1, bounds.width);
    height = Math.max(1, bounds.height);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  };

  const signalY = (signal, progress, time) => {
    const primary = Math.sin(progress * signal.frequency + signal.phase + time * signal.speed);
    const secondary = Math.cos(progress * signal.frequency * 2.7 - signal.phase + time * signal.speed * .58);
    return height * (signal.y + signal.amplitude * primary + signal.amplitude * .24 * secondary);
  };

  const draw = (time = 0) => {
    context.clearRect(0, 0, width, height);
    context.save();
    context.globalCompositeOperation = "screen";

    signals.forEach((signal, index) => {
      context.beginPath();
      for (let step = 0; step <= 120; step += 1) {
        const progress = step / 120;
        const x = -width * .04 + progress * width * 1.08;
        const y = signalY(signal, progress, time);
        if (step === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.strokeStyle = `rgba(${signal.color},${signal.alpha})`;
      context.lineWidth = index === 0 ? 1.3 : 1;
      context.stroke();

      const progress = ((time * signal.speed * .035 + signal.phase * .08) % 1 + 1) % 1;
      const x = progress * width;
      const y = signalY(signal, progress, time);
      context.beginPath();
      context.arc(x, y, index === 0 ? 3.5 : 2.5, 0, Math.PI * 2);
      context.fillStyle = `rgba(${signal.color},.9)`;
      context.fill();
      context.beginPath();
      context.arc(x, y, 14 + index * 5, 0, Math.PI * 2);
      context.strokeStyle = `rgba(${signal.color},.12)`;
      context.stroke();
    });

    context.restore();
    animationId = window.requestAnimationFrame(draw);
  };

  resize();
  draw(0);
  animationId = window.requestAnimationFrame(draw);

  window.addEventListener("resize", resize);
  window.addEventListener("pagehide", () => window.cancelAnimationFrame(animationId));
})();

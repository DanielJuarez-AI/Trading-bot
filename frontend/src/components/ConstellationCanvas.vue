<template>
  <section class="constellation-section">
    <div class="chart-header">
      <div>
        <h2>🌌 Orquesta Estelar de Agentes (Local IA): 1 Estrella por Agente &amp; Fotones con Trayectoria Curva</h2>
        <p style="font-size: 0.8rem; color: var(--text-muted)">
          Cada agente autónomo local está representado por una sola estrella brillante; la información viaja como un fotón describiendo una pequeña curva suave.
        </p>
      </div>
      <span style="font-size: 0.78rem; color: var(--poly-blue); font-weight: 600">
        Stream 1ms Activo (Polymarket / MEXC)
      </span>
    </div>

    <div class="constellation-canvas-wrap">
      <canvas ref="skyCanvas"></canvas>
    </div>

    <div class="bus-grid">
      <div v-for="msg in messageBus" :key="msg.id" class="bus-msg">
        <div class="bus-msg-head">
          <span>✦ [{{ msg.id }}] {{ msg.from }} &rarr; {{ msg.to }}</span>
          <span>{{ msg.time }}</span>
        </div>
        <div class="bus-msg-body">{{ msg.summary }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue';
import type { MultiAgentPayload, TrendDirection } from '../types/trading';

const props = defineProps<{
  multiAgent: MultiAgentPayload | null;
  layaTrend: TrendDirection;
  layaConfidence: number;
  virtualBankroll: number;
}>();

const skyCanvas = ref<HTMLCanvasElement | null>(null);
let animFrameId = 0;

const messageBus = computed(() => props.multiAgent?.message_bus || []);

interface CurvedPhoton {
  from: number;
  to: number;
  t: number;
  speed: number;
  curveOffset: number;
  color: string;
  label: string;
}

const curvedPhotons: CurvedPhoton[] = [
  { from: 0, to: 1, t: 0.05, speed: 0.0075, curveOffset: -46, color: '#38bdf8', label: 'MSG-1: Vol 5m & Oráculo' },
  { from: 1, to: 2, t: 0.38, speed: 0.0075, curveOffset: -46, color: '#a855f7', label: 'MSG-2: Tendencia & Confianza' },
  { from: 2, to: 3, t: 0.68, speed: 0.0075, curveOffset: -46, color: '#f59e0b', label: 'MSG-3: Kelly & Veto' },
  { from: 3, to: 1, t: 0.22, speed: 0.0055, curveOffset: 72, color: '#10b981', label: 'MSG-4: Recompensa R_t' },
];

function bezierPt(p0: { x: number; y: number }, p1: { x: number; y: number }, p2: { x: number; y: number }, t: number) {
  const u = 1 - t;
  return {
    x: u * u * p0.x + 2 * u * t * p1.x + t * t * p2.x,
    y: u * u * p0.y + 2 * u * t * p1.y + t * t * p2.y,
  };
}

function resizeSky() {
  if (!skyCanvas.value || !skyCanvas.value.parentElement) return;
  const r = skyCanvas.value.parentElement.getBoundingClientRect();
  skyCanvas.value.width = r.width;
  skyCanvas.value.height = r.height;
}

function animateConstellation() {
  const canvas = skyCanvas.value;
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const w = canvas.width;
  const h = canvas.height;
  const time = performance.now() * 0.0025;
  ctx.clearRect(0, 0, w, h);

  const ag = props.multiAgent?.agents || {};
  const cy = h * 0.5;
  const stars = [
    {
      title: '1. Market Scout',
      sub: ag.scout ? `${ag.scout.regime}` : 'Oráculo & Vol 5m',
      x: w * 0.14,
      y: cy,
      color: '#38bdf8',
    },
    {
      title: '2. Laya RL Brain (Local)',
      sub: `Tendencia: ${props.layaTrend} (${(props.layaConfidence * 100).toFixed(1)}%)`,
      x: w * 0.38,
      y: cy,
      color: '#c084fc',
    },
    {
      title: '3. Risk & Kelly',
      sub: ag.risk ? `Kelly: $${ag.risk.stake_usd}` : 'Gestión de Riesgo',
      x: w * 0.62,
      y: cy,
      color: '#f59e0b',
    },
    {
      title: '4. Executor CLOB',
      sub: `Banca: $${props.virtualBankroll.toFixed(2)}`,
      x: w * 0.86,
      y: cy,
      color: '#10b981',
    },
  ];

  for (const p of curvedPhotons) {
    const sA = stars[p.from];
    const sB = stars[p.to];
    const ctrl = {
      x: (sA.x + sB.x) * 0.5,
      y: (sA.y + sB.y) * 0.5 + p.curveOffset,
    };

    ctx.save();
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.18)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([4, 5]);
    ctx.beginPath();
    ctx.moveTo(sA.x, sA.y);
    ctx.quadraticCurveTo(ctrl.x, ctrl.y, sB.x, sB.y);
    ctx.stroke();
    ctx.restore();

    p.t += p.speed;
    if (p.t > 1.0) p.t = 0.0;

    for (let k = 0; k < 12; k++) {
      const tk = Math.max(0, p.t - k * 0.008);
      const pt = bezierPt(sA, ctrl, sB, tk);
      ctx.fillStyle = p.color;
      ctx.globalAlpha = (1 - k / 12) * 0.75;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, Math.max(1.2, 4.2 * (1 - k / 12)), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1.0;

    const head = bezierPt(sA, ctrl, sB, p.t);
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(head.x, head.y, 4.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = p.color;
    ctx.font = 'bold 11px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(p.label, head.x, head.y + (p.curveOffset < 0 ? -12 : 18));
  }

  stars.forEach((st, idx) => {
    const pulse = 1 + 0.16 * Math.sin(time * 2 + idx);
    const grad = ctx.createRadialGradient(st.x, st.y, 2, st.x, st.y, 36 * pulse);
    grad.addColorStop(0, st.color);
    grad.addColorStop(0.35, 'rgba(255, 255, 255, 0.14)');
    grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(st.x, st.y, 36 * pulse, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(st.x - 13 * pulse, st.y);
    ctx.lineTo(st.x + 13 * pulse, st.y);
    ctx.moveTo(st.x, st.y - 13 * pulse);
    ctx.lineTo(st.x, st.y + 13 * pulse);
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(st.x, st.y, 5.2, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 12.5px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(st.title, st.x, st.y + 42);

    ctx.fillStyle = st.color;
    ctx.font = '11px Consolas, monospace';
    ctx.fillText(st.sub, st.x, st.y + 59);
  });

  animFrameId = requestAnimationFrame(animateConstellation);
}

onMounted(() => {
  resizeSky();
  window.addEventListener('resize', resizeSky);
  animFrameId = requestAnimationFrame(animateConstellation);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeSky);
  cancelAnimationFrame(animFrameId);
});
</script>

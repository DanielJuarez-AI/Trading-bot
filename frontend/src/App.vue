<template>
  <div>
    <!-- CABECERA OSCURA PRINCIPAL (POLYMARKET + MEXC + LOCAL RL) -->
    <header>
      <div class="brand">
        <div class="btc-badge">&#8383;</div>
        <div>
          <h1>BTC Up or Down 5m &bull; Polymarket &amp; MEXC Live vs. Modelo Laya AI (Local)</h1>
          <p>{{ windowSubtitle }}</p>
        </div>
      </div>

      <div class="controls">
        <div class="control-group">
          <label for="oracleSelect">Fuente Precio Real (Oráculo 1ms)</label>
          <select id="oracleSelect" v-model="currentOracle" @change="onOracleChange">
            <option value="polymarket_rtds">Polymarket RTDS Oficial (Chainlink BTC/USD 1ms)</option>
            <option value="mexc">MEXC Exchange (BTC_USDT Spot/Futures 1ms)</option>
            <option value="coinbase">Coinbase BTC-USD (Spot Directo)</option>
            <option value="binance">Binance BTC-USDT (BookTicker 1ms)</option>
          </select>
        </div>

        <div class="control-group">
          <label for="windowOffsetSelect">Sincronía Reloj 5m Polymarket</label>
          <select id="windowOffsetSelect" v-model.number="windowOffsetSec" @change="onWindowOffsetChange">
            <option :value="0">Ventana Actual Exacta (UTC Atómico)</option>
            <option :value="-300">Ventana Anterior (-5m)</option>
            <option :value="300">Siguiente Ventana (+5m Pre-Cierre)</option>
          </select>
        </div>

        <div class="control-group">
          <label for="customSlugInput">URL / Slug Polymarket (opcional)</label>
          <input
            id="customSlugInput"
            v-model="customPolySlug"
            type="text"
            placeholder="Auto (ej. btc-updown-5m-...)"
            style="width: 175px"
            @change="initInitialPriceHistory"
          />
        </div>

        <div class="control-group">
          <label for="manualBeatInput">Fijar Price To Beat ($ opcional)</label>
          <input
            id="manualBeatInput"
            v-model.number="manualBeatVal"
            type="number"
            step="0.01"
            placeholder="Auto (Oficial 5m)"
            style="width: 145px"
            @input="onManualBeatInput"
          />
        </div>

        <button class="btn-rl" @click="syncAgentsBackground('/api/rl_boost')">⚡ +35 Épocas RL Local</button>
      </div>
    </header>

    <!-- SECCIÓN 1: TERMINAL DE APUESTAS EN VIVO -->
    <LiveBetTerminal
      :latency-text="latencyText"
      :helper-notice="helperNotice"
      :active-bet="activeVirtualBet"
      :auto-bet="autoBet"
      :laya-trend="layaTrend"
      :laya-confidence="layaConfidence"
      :selected-direction="selectedDirection"
      :up-cents="currentUpCents"
      :down-cents="currentDownCents"
      :virtual-bankroll="virtualBankroll"
      :live-spot-price="liveSpotPrice"
      :price-to-beat="priceToBeat"
      :session-wins="sessionWins"
      :session-losses="sessionLosses"
      @open-bet="openVirtualBet"
      @toggle-auto="autoBet = $event"
      @cashout="settleVirtualBet(true)"
      @reset-bankroll="resetBankroll"
      @select-direction="selectedDirection = $event"
    >
      <template #equity-chart>
        <canvas ref="equityChartCanvas"></canvas>
      </template>
    </LiveBetTerminal>

    <!-- SECCIÓN 2: TARJETAS KPI -->
    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-title">Resultado Booleano &amp; Confianza Laya (Local)</div>
        <div class="kpi-value">
          <span class="bool-pill" :class="layaBoolean ? 'bool-true' : 'bool-false'">
            {{ layaBoolean ? 'TRUE' : 'FALSE' }}
          </span>
          <span style="font-size: 1.15rem; color: var(--laya-purple)">{{ (layaConfidence * 100).toFixed(1) }}%</span>
        </div>
        <div class="kpi-sub">{{ kpiCalibSub }}</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-title">Tendencia Modelo (Compra Up / Down)</div>
        <div class="kpi-value">
          <span :class="layaTrend === 'UP' ? 'trend-up-pill' : 'trend-down-pill'">
            {{ layaTrend === 'UP' ? '▲ COMPRA UP' : '▼ COMPRA DOWN' }}
          </span>
        </div>
        <div class="kpi-sub">Cuotas Polymarket: Up {{ currentUpCents }}¢ / Down {{ currentDownCents }}¢</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-title">Price To Beat (Apertura 5m)</div>
        <div class="kpi-value" style="color: #cbd5e1">{{ fmtUsd(priceToBeat) }}</div>
        <div class="kpi-sub">
          Distancia al cierre: {{ liveSpotPrice - priceToBeat >= 0 ? '+' : '' }}${{ (liveSpotPrice - priceToBeat).toFixed(2) }} USD
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-title">Current Price ({{ currentOracle.toUpperCase() }} Live)</div>
        <div class="kpi-value" style="color: var(--btc-orange)">{{ fmtUsd(liveSpotPrice) }}</div>
        <div class="kpi-sub">Stream en tiempo real (~1 ms)</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-title">Predicción Laya (5m) &amp; Diferencia</div>
        <div class="kpi-value" style="color: var(--laya-purple)">{{ fmtUsd(layaPredictedPrice) }}</div>
        <div class="kpi-sub">
          Diferencia Laya vs Real: {{ layaPredictedPrice - liveSpotPrice >= 0 ? '+' : '' }}${{ (layaPredictedPrice - liveSpotPrice).toFixed(2) }} USD
        </div>
      </div>
    </section>

    <!-- SECCIÓN 3: GRÁFICA PRINCIPAL ESTILO POLYMARKET + SUPERPOSICIÓN LAYA -->
    <section class="charts-container">
      <div class="chart-card">
        <div class="poly-overlay-bar">
          <div class="poly-prices-left">
            <div>
              <span class="p-label">Price To Beat</span>
              <span class="p-beat">{{ fmtUsd(priceToBeat) }}</span>
            </div>
            <div>
              <span class="p-label" style="color: var(--btc-orange)">Current Price (Polymarket / MEXC)</span>
              <span class="p-current">{{ fmtUsd(liveSpotPrice) }}</span>
            </div>
            <div>
              <span class="p-label" style="color: var(--laya-purple)">Predicción Superpuesta Laya (+15s)</span>
              <span class="p-laya">{{ fmtUsd(layaPredictedPrice) }}</span>
            </div>
          </div>

          <div class="poly-timer-box">
            <div class="countdown-red">
              <div>
                <span class="cd-num">{{ timerMins }}</span>
                <span class="cd-lbl">MINS</span>
              </div>
              <div>
                <span class="cd-num">{{ timerSecs }}</span>
                <span class="cd-lbl">SECS</span>
              </div>
              <div>
                <span class="cd-num" style="font-size: 1.15rem; color: #38bdf8">{{ timerMs }}</span>
                <span class="cd-lbl">MS (1ms)</span>
              </div>
            </div>
            <div style="font-size: 1.15rem; font-weight: 800; color: #64748b">&#9671; Polymarket &bull; MEXC</div>
          </div>
        </div>

        <div class="chart-header">
          <h2>1. Gráfica en Tiempo Real (`BTC Up or Down 5m`) + Superposición de Predicción y Tendencia de Laya</h2>
          <div class="legend-tags">
            <span><i class="dot" style="background: var(--btc-orange)"></i>Precio Real (Tick a Tick)</span>
            <span><i class="dot" style="background: var(--laya-purple)"></i>Predicción Modelo Laya (Superpuesta)</span>
            <span><i class="dot" style="background: #94a3b8"></i>Price To Beat (Meta 5m)</span>
          </div>
        </div>

        <div class="canvas-wrap">
          <canvas ref="overlayChartCanvas"></canvas>
        </div>
      </div>

      <div class="charts-row-2">
        <div class="chart-card">
          <div class="chart-header">
            <h2>2. Diferencia Instantánea (&Delta; = Predicción Laya &minus; Precio Real en USD)</h2>
          </div>
          <div class="canvas-wrap-sm">
            <canvas ref="diffChartCanvas"></canvas>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-header">
            <h2>3. Evolución del Aprendizaje por Refuerzo Local (Fiabilidad de Confianza y Recompensa RL)</h2>
          </div>
          <div class="canvas-wrap-sm">
            <canvas ref="rlChartCanvas"></canvas>
          </div>
        </div>
      </div>
    </section>

    <!-- SECCIÓN 4: BITÁCORA DE APUESTAS -->
    <section class="table-card">
      <div class="chart-header">
        <h2>Bitácora de Apuestas Simuladas en Tiempo Real (Contabilidad CLOB &bull; Ventanas 5m)</h2>
      </div>
      <table>
        <thead>
          <tr>
            <th># / Ticket</th>
            <th>Hora</th>
            <th>Dirección</th>
            <th>BTC Entrada &rarr; Salida</th>
            <th>Confianza Laya</th>
            <th>Inversión ($ USD)</th>
            <th>Resultado</th>
            <th>ROI Neto</th>
            <th>PnL ($ USD)</th>
            <th>Banca Ficticia</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in virtualTradesHistory.slice(0, 15)" :key="t.id">
            <td><strong style="color: var(--rl-gold)">{{ t.id }}</strong></td>
            <td>{{ t.time }}</td>
            <td>
              <span :class="t.direction === 'UP' ? 'trend-up-pill' : 'trend-down-pill'" style="font-size: 0.7rem; padding: 2px 6px">
                {{ t.direction }}
              </span>
            </td>
            <td>{{ t.btc_move }}</td>
            <td>{{ t.conf }}%</td>
            <td>${{ t.stake.toFixed(2) }}</td>
            <td>
              <span
                class="bool-pill"
                :class="t.pnl >= 0 ? 'bool-true' : 'bool-false'"
                style="font-size: 0.7rem; padding: 2px 7px"
              >
                {{ t.outcome }}
              </span>
            </td>
            <td :class="t.pnl >= 0 ? 'diff-positive' : 'diff-negative'">{{ t.roi >= 0 ? '+' : '' }}{{ t.roi }}%</td>
            <td :class="t.pnl >= 0 ? 'diff-positive' : 'diff-negative'" style="font-weight: 700">
              {{ t.pnl >= 0 ? '+' : '' }}${{ t.pnl.toFixed(2) }}
            </td>
            <td><strong>${{ t.bankroll.toFixed(2) }}</strong></td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- SECCIÓN 5: CONSTELACIÓN MINIMALISTA EN LA PARTE INFERIOR -->
    <ConstellationCanvas
      :multi-agent="latestMa"
      :laya-trend="layaTrend"
      :laya-confidence="layaConfidence"
      :virtual-bankroll="virtualBankroll"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import Chart from 'chart.js/auto';
import LiveBetTerminal from './components/LiveBetTerminal.vue';
import ConstellationCanvas from './components/ConstellationCanvas.vue';
import { RealtimeMarketFeedManager } from './services/marketFeeds';
import type {
  ActiveVirtualBet,
  MultiAgentPayload,
  OracleSource,
  RlMetricsPayload,
  TrendDirection,
  VirtualTradeRecord,
} from './types/trading';

const currentOracle = ref<OracleSource>('polymarket_rtds');
const windowOffsetSec = ref<number>(0);
const customPolySlug = ref<string>('');
const manualBeatVal = ref<number | null>(null);
const officialPolyPriceToBeat = ref<number | null>(null);
const polyOfficialEndDateMs = ref<number | null>(null);
const activePolySlug = ref<string>('');

const priceToBeat = ref<number>(0);
const currentWindowStartBucket = ref<number>(0);
const liveSpotPrice = ref<number>(0);
const layaPredictedPrice = ref<number>(0);
const layaConfidence = ref<number>(0.72);
const layaOptimalThreshold = ref<number>(0.54);
const layaTrend = ref<TrendDirection>('UP');
const layaBoolean = ref<boolean>(true);
const currentUpCents = ref<number>(54);
const currentDownCents = ref<number>(47);
const selectedDirection = ref<TrendDirection>('UP');

const virtualBankroll = ref<number>(1000.0);
const activeVirtualBet = ref<ActiveVirtualBet | null>(null);
const autoBet = ref<boolean>(false);
const sessionWins = ref<number>(0);
const sessionLosses = ref<number>(0);
const virtualTradesHistory = ref<VirtualTradeRecord[]>([]);
const equityCurvePoints = ref<number[]>([1000.0]);
let betSeq = 1;

const latencyText = ref<string>('⚡ LATENCIA: ~1ms (POLY-RTDS)');
const helperNotice = ref<string>(
  '👉 <strong>Contabilidad Real CLOB:</strong> Al apostar se descuenta el monto de tu caja. Se liquida a $1.00/share al cerrar los 5m (o al Bid actual si vendes antes).'
);
const windowSubtitle = ref<string>('Sincronizado con Reloj Atómico UTC • Ventana 5m');
const kpiCalibSub = ref<string>('Fiabilidad RL Local (1 − Brier): --%');

const timerMins = ref<string>('04');
const timerSecs = ref<string>('59');
const timerMs = ref<string>('000');

const latestMa = ref<MultiAgentPayload | null>(null);
const latestRl = ref<RlMetricsPayload | null>(null);

const overlayChartCanvas = ref<HTMLCanvasElement | null>(null);
const diffChartCanvas = ref<HTMLCanvasElement | null>(null);
const rlChartCanvas = ref<HTMLCanvasElement | null>(null);
const equityChartCanvas = ref<HTMLCanvasElement | null>(null);

let overlayChartInstance: Chart | null = null;
let diffChartInstance: Chart | null = null;
let rlChartInstance: Chart | null = null;
let equityChartInstance: Chart | null = null;

const MAX_POINTS = 60;
let tickLabels: string[] = [];
let tickRealPrices: number[] = [];
let tickLayaPrices: number[] = [];
let tickDiffs: number[] = [];
let lastChartPushMs = 0;
let lastRenderFrameMs = 0;

function npClip(v: number, minV: number, maxV: number): number {
  return Math.max(minV, Math.min(maxV, v));
}

function fmtUsd(v: number): string {
  return `$${Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const feedManager = new RealtimeMarketFeedManager(
  (price: number, sourceTag: string) => onNewRealtimeTick(price, sourceTag),
  (upC: number, downC: number) => {
    currentUpCents.value = upC;
    currentDownCents.value = downC;
  }
);

function onOracleChange() {
  feedManager.currentOracle = currentOracle.value;
  initInitialPriceHistory();
}

function onWindowOffsetChange() {
  polyOfficialEndDateMs.value = null;
  officialPolyPriceToBeat.value = null;
  initInitialPriceHistory();
}

function onManualBeatInput() {
  if (manualBeatVal.value && manualBeatVal.value > 1000) {
    priceToBeat.value = manualBeatVal.value;
    recomputeLayaRealtime();
  } else if (officialPolyPriceToBeat.value) {
    priceToBeat.value = officialPolyPriceToBeat.value;
    recomputeLayaRealtime();
  }
}

async function syncPolymarket5mContract() {
  const sync = await feedManager.fetchPolymarket5mSync(windowOffsetSec.value, customPolySlug.value);
  if (!sync) return;
  if (sync.slug) activePolySlug.value = sync.slug;
  if (sync.end_date) {
    const parsed = Date.parse(sync.end_date);
    if (!isNaN(parsed)) polyOfficialEndDateMs.value = parsed;
  }
  if (sync.price_to_beat && sync.price_to_beat > 1000) {
    officialPolyPriceToBeat.value = +Number(sync.price_to_beat).toFixed(2);
    if (!manualBeatVal.value) {
      priceToBeat.value = officialPolyPriceToBeat.value;
    }
  }
}

async function initInitialPriceHistory() {
  try {
    await feedManager.syncAtomicClock();
    await syncPolymarket5mContract();

    const realNowMs = feedManager.getAtomicNowMs();
    currentWindowStartBucket.value = Math.floor((realNowMs + windowOffsetSec.value * 1000) / 300000);
    const exactWindowStartMs = currentWindowStartBucket.value * 300000;

    const k5Res = await fetch(
      `https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime=${exactWindowStartMs}&limit=1`
    );
    const k5 = await k5Res.json();
    let binanceOpen5m = 0;
    if (k5 && k5.length) {
      binanceOpen5m = parseFloat(k5[0][1]);
    }

    const k1sRes = await fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1s&limit=60');
    const k1s = await k1sRes.json();

    let basisOffset = 0.0;
    if (currentOracle.value === 'polymarket_rtds' || currentOracle.value === 'coinbase') {
      try {
        const cbRes = await fetch('https://api.coinbase.com/v2/prices/BTC-USD/spot');
        const cbJson = await cbRes.json();
        const cbSpot = parseFloat(cbJson.data.amount);
        const binLast = parseFloat(k1s[k1s.length - 1][4]);
        if (!isNaN(cbSpot) && !isNaN(binLast)) {
          basisOffset = cbSpot - binLast;
          feedManager.chainlinkBasisOffset = basisOffset;
        }
      } catch {
        // Fallback
      }
    }

    if (!manualBeatVal.value && !officialPolyPriceToBeat.value && binanceOpen5m > 1000) {
      priceToBeat.value = +(binanceOpen5m + basisOffset).toFixed(2);
    }

    tickLabels = [];
    tickRealPrices = [];
    tickLayaPrices = [];
    tickDiffs = [];

    for (let i = 0; i < k1s.length; i++) {
      const ts = k1s[i][0];
      const p = +(parseFloat(k1s[i][4]) + basisOffset).toFixed(2);
      const lbl = new Date(ts).toLocaleTimeString('en-US', {
        hour12: true,
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
      });
      tickLabels.push(lbl);
      tickRealPrices.push(p);

      const prevP = i > 0 ? tickRealPrices[i - 1] : p;
      const prevPrevP = i > 3 ? tickRealPrices[i - 4] : prevP;
      const mom = (p - prevPrevP) * 1.45 + (p - priceToBeat.value) * 0.18;
      const predP = +(p + mom).toFixed(2);
      tickLayaPrices.push(predP);
      tickDiffs.push(+(predP - p).toFixed(2));
    }

    liveSpotPrice.value = tickRealPrices[tickRealPrices.length - 1];
    recomputeLayaRealtime();
    renderRealtimeCharts();
    renderEquityChart();
  } catch (e) {
    console.error('Error inicializando historial 1s:', e);
  }
}

function onNewRealtimeTick(price: number, sourceTag: string) {
  if (isNaN(price) || price <= 0) return;
  const nowPerf = performance.now();
  liveSpotPrice.value = +price.toFixed(2);
  const atomicNowMs = feedManager.getAtomicNowMs();

  const bucket = Math.floor((atomicNowMs + windowOffsetSec.value * 1000) / 300000);
  if (currentWindowStartBucket.value !== 0 && bucket !== currentWindowStartBucket.value) {
    currentWindowStartBucket.value = bucket;
    if (activeVirtualBet.value) {
      settleVirtualBet(false);
    }
    officialPolyPriceToBeat.value = null;
    if (!manualBeatVal.value) {
      priceToBeat.value = liveSpotPrice.value;
    }
    syncPolymarket5mContract();
  } else if (currentWindowStartBucket.value === 0) {
    currentWindowStartBucket.value = bucket;
  }

  if (!priceToBeat.value) priceToBeat.value = liveSpotPrice.value;
  recomputeLayaRealtime();

  if (atomicNowMs - lastChartPushMs >= 500) {
    lastChartPushMs = atomicNowMs;
    const lbl = new Date(atomicNowMs).toLocaleTimeString('en-US', {
      hour12: true,
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
    });
    tickLabels.push(lbl);
    tickRealPrices.push(liveSpotPrice.value);
    tickLayaPrices.push(layaPredictedPrice.value);
    tickDiffs.push(+(layaPredictedPrice.value - liveSpotPrice.value).toFixed(2));

    if (tickLabels.length > MAX_POINTS) {
      tickLabels.shift();
      tickRealPrices.shift();
      tickLayaPrices.shift();
      tickDiffs.shift();
    }
  } else if (tickRealPrices.length > 0) {
    tickRealPrices[tickRealPrices.length - 1] = liveSpotPrice.value;
    tickLayaPrices[tickLayaPrices.length - 1] = layaPredictedPrice.value;
    tickDiffs[tickDiffs.length - 1] = +(layaPredictedPrice.value - liveSpotPrice.value).toFixed(2);
  }

  if (nowPerf - lastRenderFrameMs >= 16) {
    lastRenderFrameMs = nowPerf;
    const driftTag =
      feedManager.pcClockDriftSec !== 0
        ? ` | Reloj PC corregido: ${feedManager.pcClockDriftSec > 0 ? '-' : '+'}${Math.abs(feedManager.pcClockDriftSec)}s`
        : '';
    latencyText.value = `⚡ LATENCIA: ~1ms (${sourceTag})${driftTag}`;
    renderRealtimeCharts();
  }
}

function recomputeLayaRealtime() {
  const n = tickRealPrices.length;
  if (n < 4) {
    layaPredictedPrice.value = liveSpotPrice.value;
    return;
  }

  const pNow = liveSpotPrice.value;
  const p3 = tickRealPrices[Math.max(0, n - 4)];
  const p10 = tickRealPrices[Math.max(0, n - 11)];
  const vShort = pNow - p3;
  const vMed = pNow - p10;
  const distFromBeat = pNow - priceToBeat.value;

  let sumSq = 0;
  for (let i = 1; i < n; i++) {
    const d = tickRealPrices[i] - tickRealPrices[i - 1];
    sumSq += d * d;
  }
  const tickStd = Math.sqrt(sumSq / n) || 2.5;

  const momentumScore = 0.62 * vShort + 0.38 * vMed + 0.22 * distFromBeat;
  const projectedDelta = npClip(momentumScore * 1.35, -tickStd * 6.5, tickStd * 6.5);
  layaPredictedPrice.value = +(pNow + projectedDelta).toFixed(2);

  layaTrend.value = layaPredictedPrice.value >= priceToBeat.value ? 'UP' : 'DOWN';

  const zSignal = Math.abs(layaPredictedPrice.value - priceToBeat.value) / Math.max(4.0, tickStd * 2.2);
  const rawConf = 1.0 / (1.0 + Math.exp(-(0.35 + 1.15 * zSignal)));
  layaConfidence.value = Math.min(0.965, Math.max(0.51, rawConf));
  layaBoolean.value = layaConfidence.value >= layaOptimalThreshold.value;

  const probUp = npClip(0.5 + (distFromBeat / Math.max(18.0, tickStd * 5.0)) * 0.38, 0.06, 0.94);
  currentUpCents.value = Math.round(probUp * 100);
  currentDownCents.value = Math.max(1, 101 - currentUpCents.value);

  if (activeVirtualBet.value) {
    const b = activeVirtualBet.value;
    const btcMoveFromEntry = b.direction === 'UP' ? pNow - b.entry_btc : b.entry_btc - pNow;
    const centsDelta = (btcMoveFromEntry / Math.max(15.0, tickStd * 4.5)) * 28.0;
    const currentBidCents = npClip(b.entry_ask_cents - 1.5 + centsDelta, 2.0, 98.0);
    const markVal = +(b.shares * (currentBidCents / 100.0)).toFixed(2);
    const fpnl = +(markVal - b.stake_usd).toFixed(2);
    const froi = +((fpnl / b.stake_usd) * 100).toFixed(2);

    b.current_bid_cents = +currentBidCents.toFixed(1);
    b.mark_value_usd = markVal;
    b.floating_pnl = fpnl;
    b.floating_roi = froi;
    b.winning_now = b.direction === 'UP' ? pNow >= priceToBeat.value : pNow < priceToBeat.value;
  }
}

function openVirtualBet(stakeMode: string) {
  if (!liveSpotPrice.value || liveSpotPrice.value <= 0) return;

  if (activeVirtualBet.value && stakeMode === 'kelly_main_btn') {
    helperNotice.value = `<span style="color:#f59e0b;font-weight:700;">⚠️ Ya tienes la apuesta ${activeVirtualBet.value.id} ($${activeVirtualBet.value.stake_usd.toFixed(2)} a ${activeVirtualBet.value.direction}) en juego. Espera al cierre del reloj (00:00) o usa "⚡ Vender Posición (Cashout CLOB)" para cerrar al precio Bid actual.</span>`;
    return;
  }

  const dir: TrendDirection =
    stakeMode === 'kelly' || stakeMode === 'kelly_main_btn' ? layaTrend.value : selectedDirection.value;
  selectedDirection.value = dir;
  const midCents = dir === 'UP' ? currentUpCents.value : currentDownCents.value;
  const askCents = Math.min(98, Math.max(3, midCents + 1));
  const askProb = askCents / 100.0;

  let stake = 25.0;
  if (stakeMode === 'kelly' || stakeMode === 'kelly_main_btn') {
    const b = (1 - askProb) / askProb;
    const p = layaConfidence.value;
    const kellyFrac = Math.min(0.08, Math.max(0.02, ((p * b - (1 - p)) / b) * 0.25));
    stake = +(virtualBankroll.value * kellyFrac).toFixed(2);
  } else {
    stake = parseFloat(stakeMode) || 25.0;
  }

  if (virtualBankroll.value < 1.0) return;
  if (stake > virtualBankroll.value) stake = +virtualBankroll.value.toFixed(2);

  virtualBankroll.value = +(virtualBankroll.value - stake).toFixed(2);
  const newShares = +(stake / askProb).toFixed(2);

  if (activeVirtualBet.value && activeVirtualBet.value.direction === dir) {
    const totalStake = +(activeVirtualBet.value.stake_usd + stake).toFixed(2);
    const totalShares = +(activeVirtualBet.value.shares + newShares).toFixed(2);
    activeVirtualBet.value.stake_usd = totalStake;
    activeVirtualBet.value.shares = totalShares;
    activeVirtualBet.value.entry_ask_cents = Math.round((totalStake / totalShares) * 100);
  } else {
    if (activeVirtualBet.value) {
      settleVirtualBet(true);
    }
    activeVirtualBet.value = {
      id: `BET-${String(betSeq++).padStart(3, '0')}`,
      opened_at: new Date(feedManager.getAtomicNowMs()).toLocaleTimeString(),
      direction: dir,
      entry_ask_cents: askCents,
      current_bid_cents: Math.max(1, askCents - 1.5),
      entry_btc: liveSpotPrice.value,
      stake_usd: stake,
      shares: newShares,
      mark_value_usd: +(newShares * (Math.max(1, askCents - 1.5) / 100.0)).toFixed(2),
      floating_pnl: -+(stake * 0.02).toFixed(2),
      floating_roi: -2.0,
      winning_now: dir === 'UP' ? liveSpotPrice.value >= priceToBeat.value : liveSpotPrice.value < priceToBeat.value,
    };
  }

  helperNotice.value = `✅ <strong>Orden Ejecutada (${activeVirtualBet.value.id}):</strong> Se descontaron <strong>$${stake.toFixed(2)}</strong> de tu caja. Compraste <strong>${newShares.toFixed(2)} shares ${dir}</strong> a ${askCents}¢.`;
  recomputeLayaRealtime();
}

function settleVirtualBet(isEarlyCashout = false) {
  if (!activeVirtualBet.value) return;
  const b = activeVirtualBet.value;
  recomputeLayaRealtime();

  let payoutUsd = 0.0;
  let pnl = 0.0;
  let roi = 0.0;
  let won = false;
  let outcomeLabel = '';

  if (isEarlyCashout) {
    payoutUsd = +b.mark_value_usd.toFixed(2);
    pnl = +(payoutUsd - b.stake_usd).toFixed(2);
    roi = +((pnl / b.stake_usd) * 100).toFixed(2);
    won = pnl > 0;
    outcomeLabel = won ? 'CASHOUT (+)' : 'CASHOUT (-)';
  } else {
    won = b.direction === 'UP' ? liveSpotPrice.value >= priceToBeat.value : liveSpotPrice.value < priceToBeat.value;
    if (won) {
      payoutUsd = +(b.shares * 1.0).toFixed(2);
      pnl = +(payoutUsd - b.stake_usd).toFixed(2);
      roi = +((pnl / b.stake_usd) * 100).toFixed(2);
      outcomeLabel = 'GANADA (5m)';
    } else {
      payoutUsd = 0.0;
      pnl = -b.stake_usd;
      roi = -100.0;
      outcomeLabel = 'PERDIDA (5m)';
    }
  }

  if (won) sessionWins.value += 1;
  else sessionLosses.value += 1;

  virtualBankroll.value = +(virtualBankroll.value + payoutUsd).toFixed(2);
  equityCurvePoints.value.push(virtualBankroll.value);

  virtualTradesHistory.value.unshift({
    id: b.id,
    time: new Date(feedManager.getAtomicNowMs()).toLocaleTimeString(),
    direction: b.direction,
    btc_move: `$${b.entry_btc.toLocaleString()} → $${liveSpotPrice.value.toLocaleString()}`,
    conf: (layaConfidence.value * 100).toFixed(1),
    stake: b.stake_usd,
    outcome: outcomeLabel,
    roi,
    pnl,
    bankroll: virtualBankroll.value,
  });

  const sign = pnl >= 0 ? '+' : '';
  helperNotice.value = `🏁 <strong>${b.id} Liquidada (${outcomeLabel}):</strong> Retorno recibido: <strong>$${payoutUsd.toFixed(2)}</strong> (PnL: <strong>${sign}$${pnl.toFixed(2)}</strong> | Nueva Caja: <strong>$${virtualBankroll.value.toFixed(2)}</strong>).`;

  activeVirtualBet.value = null;
  renderEquityChart();

  if (!isEarlyCashout && autoBet.value) {
    setTimeout(() => openVirtualBet('kelly'), 400);
  }
}

function resetBankroll() {
  virtualBankroll.value = 1000.0;
  sessionWins.value = 0;
  sessionLosses.value = 0;
  activeVirtualBet.value = null;
  virtualTradesHistory.value = [];
  equityCurvePoints.value = [1000.0];
  renderEquityChart();
}

function updateCountdownClock() {
  const atomicNowMs = feedManager.getAtomicNowMs();
  let baseEndMs = (Math.floor((atomicNowMs + windowOffsetSec.value * 1000) / 300000) + 1) * 300000;
  if (polyOfficialEndDateMs.value && customPolySlug.value) {
    baseEndMs = polyOfficialEndDateMs.value;
  }
  const diffMs = Math.max(0, baseEndMs - atomicNowMs);
  const remSec = Math.floor(diffMs / 1000);
  const remMillis = Math.floor(diffMs % 1000);

  timerMins.value = String(Math.floor(remSec / 60)).padStart(2, '0');
  timerSecs.value = String(remSec % 60).padStart(2, '0');
  timerMs.value = String(remMillis).padStart(3, '0');

  const startWin = new Date(baseEndMs - 300000);
  const endWin = new Date(baseEndMs);
  const etFmt: Intl.DateTimeFormatOptions = {
    timeZone: 'America/New_York',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  };
  const sStr = startWin.toLocaleTimeString('en-US', etFmt);
  const eStr = endWin.toLocaleTimeString('en-US', etFmt);
  const slugText = activePolySlug.value || `btc-updown-5m-${Math.floor((baseEndMs - 300000) / 1000)}`;
  windowSubtitle.value = `Contrato: ${slugText} (${sStr} – ${eStr} ET) | Reloj Atómico UTC Sincronizado (PC: -${feedManager.pcClockDriftSec}s corregidos)`;
  requestAnimationFrame(updateCountdownClock);
}

function renderRealtimeCharts() {
  if (tickLabels.length < 2 || !overlayChartCanvas.value || !diffChartCanvas.value) return;

  const extLabels = [...tickLabels, '+5s', '+10s', '+15s'];
  const extReal = [...tickRealPrices, null, null, null];
  const stepDelta = (layaPredictedPrice.value - liveSpotPrice.value) / 3.0;
  const extLaya = [
    ...tickLayaPrices,
    +(liveSpotPrice.value + stepDelta).toFixed(2),
    +(liveSpotPrice.value + stepDelta * 2).toFixed(2),
    layaPredictedPrice.value,
  ];
  const extBeat = extLabels.map(() => priceToBeat.value);

  const ctx1 = overlayChartCanvas.value.getContext('2d');
  if (ctx1) {
    if (!overlayChartInstance) {
      const grad = ctx1.createLinearGradient(0, 0, 0, 320);
      grad.addColorStop(0, 'rgba(247, 147, 26, 0.22)');
      grad.addColorStop(1, 'rgba(247, 147, 26, 0.0)');

      overlayChartInstance = new Chart(ctx1, {
        type: 'line',
        data: {
          labels: extLabels,
          datasets: [
            {
              label: 'Polymarket / MEXC BTC Live ($)',
              data: extReal,
              borderColor: '#f7931a',
              backgroundColor: grad,
              fill: true,
              borderWidth: 2.8,
              tension: 0.28,
            },
            {
              label: 'Predicción Modelo Laya ($)',
              data: extLaya,
              borderColor: '#a855f7',
              backgroundColor: 'transparent',
              borderWidth: 2.4,
              borderDash: [5, 4],
              tension: 0.28,
            },
            {
              label: 'Price To Beat ($)',
              data: extBeat,
              borderColor: 'rgba(148, 163, 184, 0.45)',
              borderWidth: 1.4,
              borderDash: [4, 4],
              pointRadius: 0,
              fill: false,
            },
          ],
        },
        options: {
          animation: false,
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
        },
      });
    } else {
      overlayChartInstance.data.labels = extLabels;
      overlayChartInstance.data.datasets[0].data = extReal;
      overlayChartInstance.data.datasets[1].data = extLaya;
      overlayChartInstance.data.datasets[2].data = extBeat;
      overlayChartInstance.update('none');
    }
  }

  const ctx2 = diffChartCanvas.value.getContext('2d');
  if (ctx2) {
    if (!diffChartInstance) {
      diffChartInstance = new Chart(ctx2, {
        type: 'bar',
        data: {
          labels: tickLabels,
          datasets: [
            {
              label: 'Diferencia Laya - Real ($ USD)',
              data: tickDiffs,
              backgroundColor: tickDiffs.map((v) => (v >= 0 ? 'rgba(16, 185, 129, 0.75)' : 'rgba(239, 68, 68, 0.75)')),
            },
          ],
        },
        options: {
          animation: false,
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
        },
      });
    } else {
      diffChartInstance.data.labels = tickLabels;
      diffChartInstance.data.datasets[0].data = tickDiffs;
      diffChartInstance.update('none');
    }
  }
}

function renderEquityChart() {
  if (!equityChartCanvas.value) return;
  const ctxEq = equityChartCanvas.value.getContext('2d');
  if (!ctxEq) return;
  const eqLabels = equityCurvePoints.value.map((_, i) => `#${i}`);
  if (!equityChartInstance) {
    equityChartInstance = new Chart(ctxEq, {
      type: 'line',
      data: {
        labels: eqLabels,
        datasets: [
          {
            data: equityCurvePoints.value,
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.14)',
            fill: true,
            borderWidth: 2,
            tension: 0.25,
            pointRadius: 0,
          },
        ],
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
      },
    });
  } else {
    equityChartInstance.data.labels = eqLabels;
    equityChartInstance.data.datasets[0].data = equityCurvePoints.value;
    equityChartInstance.update('none');
  }
}

async function syncAgentsBackground(endpoint = '/api/compare') {
  try {
    const res = await fetch(endpoint);
    if (!res.ok) return;
    const data = await res.json();
    latestMa.value = data.multi_agent || null;
    latestRl.value = data.rl || null;

    if (latestRl.value?.optimal_threshold) {
      layaOptimalThreshold.value = latestRl.value.optimal_threshold;
    }
    if (latestRl.value?.calibration_index_pct) {
      kpiCalibSub.value = `Fiabilidad RL Local (1 − Brier): ${latestRl.value.calibration_index_pct.toFixed(1)}% (${latestRl.value.episodes_trained} ep)`;
    }

    if (rlChartCanvas.value && latestRl.value) {
      const calHist = latestRl.value.calibration_history || [];
      const rewHist = latestRl.value.reward_history || [];
      const epLabels = calHist.map((_, i) => `Ep ${i + 1}`);
      const ctx3 = rlChartCanvas.value.getContext('2d');
      if (ctx3) {
        if (!rlChartInstance) {
          rlChartInstance = new Chart(ctx3, {
            type: 'line',
            data: {
              labels: epLabels,
              datasets: [
                { label: 'Fiabilidad (%)', data: calHist, borderColor: '#10b981', borderWidth: 2, tension: 0.3 },
                { label: 'Recompensa RL', data: rewHist, borderColor: '#f59e0b', borderDash: [3, 3], borderWidth: 2, tension: 0.3 },
              ],
            },
            options: {
              animation: false,
              responsive: true,
              maintainAspectRatio: false,
              plugins: { legend: { display: false } },
            },
          });
        } else {
          rlChartInstance.data.labels = epLabels;
          rlChartInstance.data.datasets[0].data = calHist;
          rlChartInstance.data.datasets[1].data = rewHist;
          rlChartInstance.update('none');
        }
      }
    }
  } catch {
    // Fallback
  }
}

onMounted(() => {
  initInitialPriceHistory();
  feedManager.startAllStreams();
  requestAnimationFrame(updateCountdownClock);
  syncAgentsBackground('/api/compare');
  setInterval(() => syncAgentsBackground('/api/compare'), 3500);
  setInterval(syncPolymarket5mContract, 1200);
  setInterval(() => feedManager.syncAtomicClock(), 10000);
});
</script>

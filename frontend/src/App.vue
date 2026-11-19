<template>
  <div>
    <!-- CABECERA OSCURA PRINCIPAL (POLYMARKET + MEXC + LOCAL RL) -->
    <header>
      <div class="brand">
        <div class="btc-badge">&#8383;</div>
        <div>
          <h1>BTC Up or Down 5m &bull; Polymarket &amp; MEXC Live vs. Modelo Laya AI <span style="font-size: 0.72rem; background: rgba(16, 185, 129, 0.16); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.38); border-radius: 999px; padding: 2px 8px; vertical-align: middle; margin-left: 6px; font-weight: 700;">v1.1.0</span></h1>
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

    <!-- WORKSTATION POLYMARKET: GRÁFICA EXACTA + TRAZO LAYA (IZQ) & COLUMNA UP/DOWN (DER) -->
    <section class="poly-workstation-grid">
      <div class="poly-chart-card" :class="polyThemeMode === 'light' ? 'poly-light' : 'poly-dark'">
        <div>
          <div class="poly-header-exact">
            <div class="poly-prices-strip">
              <div>
                <span class="poly-metric-lbl">Price To Beat</span>
                <span class="poly-beat-val">{{ fmtUsd(priceToBeat) }}</span>
              </div>
              <div class="poly-v-divider"></div>
              <div>
                <span class="poly-metric-lbl" style="color: #f59e0b">
                  Current Price
                  <span :style="{ color: liveSpotPrice - priceToBeat >= 0 ? '#16a34a' : '#dc2626', fontWeight: 800 }">
                    {{ liveSpotPrice - priceToBeat >= 0 ? '▲' : '▼' }} ${{ Math.abs(liveSpotPrice - priceToBeat).toFixed(0) }}
                  </span>
                </span>
                <span class="poly-current-val">{{ fmtUsd(liveSpotPrice) }}</span>
              </div>
              <div class="poly-v-divider"></div>
              <div>
                <span class="poly-metric-lbl" style="color: #9333ea">
                  Trazo Laya (+15s)
                  <span style="font-weight: 800">
                    {{ layaPredictedPrice - liveSpotPrice >= 0 ? '+' : '' }}${{ (layaPredictedPrice - liveSpotPrice).toFixed(2) }}
                  </span>
                </span>
                <span class="poly-laya-val">{{ fmtUsd(layaPredictedPrice) }}</span>
              </div>
            </div>

            <div style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap">
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
                  <span class="cd-num" style="font-size: 1.1rem; color: #0284c7">{{ timerMs }}</span>
                  <span class="cd-lbl">MS</span>
                </div>
              </div>
              <div style="font-size: 1.15rem; font-weight: 800; color: #94a3b8">&#9671; Polymarket</div>
              <button
                style="font-size: 0.7rem; padding: 4px 9px; border-radius: 7px"
                @click="togglePolyTheme"
              >
                {{ polyThemeMode === 'light' ? '🌙 Oscuro' : '☀️ Claro Polymarket' }}
              </button>
            </div>
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 0.74rem; color: #64748b">
            <span style="font-weight: 700">BTC Up or Down 5m &bull; Gráfica Real Polymarket + Superposición de Modelo Laya</span>
            <div class="legend-tags">
              <span><i class="dot" style="background: #f59e0b"></i>Precio Real</span>
              <span><i class="dot" style="background: #a855f7"></i>Trazo Laya (+15s)</span>
              <span><i class="dot" style="background: #94a3b8"></i>Target</span>
            </div>
          </div>
        </div>

        <figure
          class="polymarket-embed"
          id="polymarket-btc-updown-5m-1795098300"
          aria-label="Polymarket prediction market: Bitcoin Up or Down - November 19, 9:25AM-9:30AM ET"
          itemscope
          itemtype="https://schema.org/WebPage"
          style="position: relative; display: block; width: 100%; margin: 0"
        >
          <a
            :href="`https://polymarket.com/event/${activePolySlug || 'btc-updown-5m-1795098300'}`"
            aria-label="View on Polymarket"
            target="_blank"
            rel="noopener"
            style="position: absolute; top: 4px; right: 12px; width: 120px; height: 24px; z-index: 10"
          ></a>
          <div class="poly-canvas-wrap">
            <div class="poly-source-pill">Source: Polymarket.com</div>
            <canvas ref="overlayChartCanvas"></canvas>
          </div>
          <figcaption
            style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0"
          >
            <strong>Bitcoin Up or Down - November 19, 9:25AM-9:30AM ET</strong><br />
            Up {{ currentUpCents }}% &middot; Down {{ currentDownCents }}%<br />
            <a :href="`https://polymarket.com/event/${activePolySlug || 'btc-updown-5m-1795098300'}`">
              View full market &amp; trade on Polymarket
            </a>
          </figcaption>
        </figure>
      </div>

      <LiveBetTerminal
        class="poly-right-col"
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
        :point1-model-conf-pct="point1ModelConfPct"
        :point2-risk-conf-pct="point2RiskConfPct"
        :dual85-passed="dual85Passed"
        :last-minute-locked="isLastMinuteLocked"
        :remaining-window-sec="remainingWindowSec"
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
    </section>

    <!-- BARRAS DE CONFIABILIDAD (CONFIANZA OPERATIVA DEL MODELO) + GRÁFICA COMPRADORES VS VENDEDORES -->
    <section class="poly-below-analytics-grid">
      <div class="chart-card">
        <div class="chart-header" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <h2>🎯 Confianza del Modelo para Ejecutar la Operación (Umbral &gt;85%)</h2>
          <span
            id="barExecSideTag"
            :class="['conf-pill', !isLastMinuteLocked && Math.min(point1ModelConfPct, point2RiskConfPct) > 85 ? 'pass' : '']"
          >
            {{ layaTrend === 'UP' ? '▲ COMPRA UP' : '▼ COMPRA DOWN' }} &bull;
            {{
              isLastMinuteLocked
                ? '🔒 Bloqueado <60s'
                : Math.min(point1ModelConfPct, point2RiskConfPct) > 85
                  ? '🚀 LISTO PARA EJECUTAR (>85%)'
                  : '⏳ Esperando >85%'
            }}
          </span>
        </div>
        <div class="reliability-list">
          <div class="reliability-bar-item">
            <div class="reliability-head">
              <span>Punto 1 &mdash; Confianza Direccional para Operar</span>
              <span style="color: #c084fc">{{ point1ModelConfPct.toFixed(1) }}%</span>
            </div>
            <div class="reliability-track">
              <span class="threshold-85-tag">85%</span>
              <div class="threshold-85-marker"></div>
              <div class="reliability-fill" :style="{ width: `${Math.min(100, point1ModelConfPct)}%`, background: point1ModelConfPct > 85 ? '#10b981' : '#a855f7' }"></div>
            </div>
          </div>

          <div class="reliability-bar-item">
            <div class="reliability-head">
              <span>Punto 2 &mdash; Viabilidad Determinista &amp; Kelly (0.25&times;)</span>
              <span style="color: #38bdf8">{{ point2RiskConfPct.toFixed(1) }}%</span>
            </div>
            <div class="reliability-track">
              <span class="threshold-85-tag">85%</span>
              <div class="threshold-85-marker"></div>
              <div class="reliability-fill" :style="{ width: `${Math.min(100, point2RiskConfPct)}%`, background: point2RiskConfPct > 85 ? '#10b981' : '#38bdf8' }"></div>
            </div>
          </div>

          <div class="reliability-bar-item">
            <div class="reliability-head">
              <span>Confianza Conjunta para Ejecutar la Orden (Mín. P1 &amp; P2 &bull; RL {{ lastSyncCalibPct.toFixed(1) }}%)</span>
              <span :style="{ color: Math.min(point1ModelConfPct, point2RiskConfPct) > 85 ? '#10b981' : '#f59e0b' }">
                {{ Math.min(point1ModelConfPct, point2RiskConfPct).toFixed(1) }}%
              </span>
            </div>
            <div class="reliability-track">
              <span class="threshold-85-tag">85%</span>
              <div class="threshold-85-marker"></div>
              <div
                class="reliability-fill"
                :style="{
                  width: `${Math.min(100, Math.min(point1ModelConfPct, point2RiskConfPct))}%`,
                  background: Math.min(point1ModelConfPct, point2RiskConfPct) > 85 ? '#10b981' : '#f59e0b',
                }"
              ></div>
            </div>
          </div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <h2>⚖️ Presión del Mercado: % Compradores vs. % Vendedores</h2>
        </div>
        <div class="tug-of-war-head">
          <span style="color: #10b981">▲ Compradores: {{ currentBuyersPct.toFixed(1) }}%</span>
          <span style="color: #ef4444">▼ Vendedores: {{ currentSellersPct.toFixed(1) }}%</span>
        </div>
        <div class="tug-of-war-track">
          <div class="tug-buyers-fill" :style="{ width: `${currentBuyersPct}%` }"></div>
          <div class="tug-sellers-fill" :style="{ width: `${currentSellersPct}%` }"></div>
        </div>
        <div style="position: relative; height: 185px; width: 100%">
          <canvas ref="buyersSellersChartCanvas"></canvas>
        </div>
      </div>
    </section>

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

    <!-- SECCIÓN 3: GRÁFICAS SECUNDARIAS -->
    <section class="charts-container">
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
const lastSyncCalibPct = ref<number>(91.13);
const point1ModelConfPct = ref<number>(0.0);
const point2RiskConfPct = ref<number>(0.0);
const dual85Passed = ref<boolean>(false);
const isLastMinuteLocked = ref<boolean>(false);
const remainingWindowSec = ref<number>(300);
let autoOperatedWindowBucket = 0;

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
const buyersSellersChartCanvas = ref<HTMLCanvasElement | null>(null);

let overlayChartInstance: Chart | null = null;
let diffChartInstance: Chart | null = null;
let rlChartInstance: Chart | null = null;
let equityChartInstance: Chart | null = null;
let buyersSellersChartInstance: Chart | null = null;

const polyThemeMode = ref<'light' | 'dark'>('light');
const currentBuyersPct = ref<number>(50.0);
const currentSellersPct = ref<number>(50.0);
let lastSyncBuyersPct = 50.0;

const MAX_POINTS = 60;
let tickLabels: string[] = [];
let tickRealPrices: number[] = [];
let tickLayaPrices: number[] = [];
let tickDiffs: number[] = [];
let tickBuyersPct: number[] = [];
let tickSellersPct: number[] = [];
let lastChartPushMs = 0;
let lastRenderFrameMs = 0;

interface FluidPoint {
  ts: number;
  real: number;
  laya: number;
}
const FLUID_WINDOW_MS = 22000;
const FLUID_LEAD_MS = 3200;
const FLUID_SAMPLE_MS = 75;
let fluidPoints: FluidPoint[] = [];
let stage1Spot = 0;
let stage1Laya = 0;
let displaySpotPrice = 0;
let displayLayaPrice = 0;
let smoothYMin = 0;
let smoothYMax = 0;
let lastFluidSampleMs = 0;
let chartHoverX: number | null = null;
let chartHoverY: number | null = null;

function togglePolyTheme() {
  polyThemeMode.value = polyThemeMode.value === 'light' ? 'dark' : 'light';
  if (overlayChartInstance) {
    overlayChartInstance.destroy();
    overlayChartInstance = null;
  }
  renderRealtimeCharts();
}

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
    tickBuyersPct = [];
    tickSellersPct = [];
    fluidPoints = [];

    const nowFluidMs = feedManager.getAtomicNowMs();
    const kLen = k1s.length;
    const startIdx = Math.max(0, kLen - 28);
    const rawCloses = k1s.map((row: any) => +(parseFloat(row[4]) + basisOffset).toFixed(2));
    const smoothCloses = rawCloses.map((val: number, idx: number) => {
      const a = rawCloses[Math.max(0, idx - 1)];
      const b = val;
      const c = rawCloses[Math.min(rawCloses.length - 1, idx + 1)];
      return +((a + b * 2.0 + c) / 4.0).toFixed(2);
    });

    for (let i = 0; i < kLen; i++) {
      const ts = k1s[i][0];
      const p = smoothCloses[i];
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
      const mom = npClip((p - prevPrevP) * 0.45 + npClip(p - priceToBeat.value, -18.0, 18.0) * 0.06, -7.5, 7.5);
      const predP = +(p + mom).toFixed(2);
      tickLayaPrices.push(predP);
      tickDiffs.push(+(predP - p).toFixed(2));

      const kVol = parseFloat(k1s[i][5] || '1');
      const kTakerBuy = parseFloat(k1s[i][9] || String(kVol * 0.5));
      const bPct = +npClip((kTakerBuy / Math.max(1e-8, kVol)) * 100.0, 5.0, 95.0).toFixed(1);
      tickBuyersPct.push(bPct);
      tickSellersPct.push(+(100.0 - bPct).toFixed(1));

      if (i >= startIdx) {
        const relTs = nowFluidMs - (kLen - 1 - i) * 1000;
        if (i > startIdx) {
          const p0 = tickRealPrices[i - 1];
          const l0 = p0 + npClip(tickLayaPrices[i - 1] - p0, -7.5, 7.5);
          const l1 = p + npClip(predP - p, -7.5, 7.5);
          const t0 = relTs - 1000;
          for (let s = 1; s <= 12; s++) {
            const f = s / 12.0;
            const ease = f * f * (3.0 - 2.0 * f);
            const tsPt = t0 + f * 1000;
            const wave = Math.sin(tsPt * 0.0082) * 0.22;
            fluidPoints.push({
              ts: tsPt,
              real: +(p0 + (p - p0) * ease + wave).toFixed(2),
              laya: +(l0 + (l1 - l0) * ease + wave * 0.6).toFixed(2),
            });
          }
        } else {
          fluidPoints.push({ ts: relTs, real: p, laya: +(p + npClip(predP - p, -7.5, 7.5)).toFixed(2) });
        }
      }
    }

    liveSpotPrice.value = tickRealPrices[tickRealPrices.length - 1];
    stage1Spot = liveSpotPrice.value;
    displaySpotPrice = liveSpotPrice.value;
    recomputeLayaRealtime();
    stage1Laya = layaPredictedPrice.value || liveSpotPrice.value;
    displayLayaPrice = stage1Laya;
    smoothYMin = 0;
    smoothYMax = 0;
    lastFluidSampleMs = nowFluidMs;

    renderRealtimeCharts();
    renderEquityChart();
  } catch (e) {
    console.error('Error inicializando historial 1s:', e);
  }
}

function onNewRealtimeTick(price: number, sourceTag: string) {
  if (isNaN(price) || price <= 0) return;
  const nowPerf = performance.now();
  if (liveSpotPrice.value > 1000 && Math.abs(price - liveSpotPrice.value) > 18.0) {
    const jumpDelta = price - liveSpotPrice.value;
    if (sourceTag === 'POLY-1MS') {
      feedManager.chainlinkBasisOffset += jumpDelta * 0.15;
    }
    price = liveSpotPrice.value + npClip(jumpDelta, -1.8, 1.8);
  }
  liveSpotPrice.value = +price.toFixed(2);
  const atomicNowMs = feedManager.getAtomicNowMs();

  const bucket = Math.floor((atomicNowMs + windowOffsetSec.value * 1000) / 300000);
  if (currentWindowStartBucket.value !== 0 && bucket !== currentWindowStartBucket.value) {
    currentWindowStartBucket.value = bucket;
    autoOperatedWindowBucket = 0;
    isLastMinuteLocked.value = false;
    if (activeVirtualBet.value) {
      settleVirtualBet(false);
    }
    officialPolyPriceToBeat.value = null;
    if (!manualBeatVal.value) {
      priceToBeat.value = liveSpotPrice.value;
    }
    helperNotice.value =
      '🔓 <strong>Nuevo periodo de 5 minutos iniciado:</strong> Apuestas rehabilitadas automáticamente. Esperando señal dual &gt;85% (Punto 1 + Punto 2).';
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
    tickBuyersPct.push(currentBuyersPct.value);
    tickSellersPct.push(currentSellersPct.value);

    if (tickLabels.length > MAX_POINTS) {
      tickLabels.shift();
      tickRealPrices.shift();
      tickLayaPrices.shift();
      tickDiffs.shift();
      tickBuyersPct.shift();
      tickSellersPct.shift();
    }
  } else if (tickRealPrices.length > 0) {
    tickRealPrices[tickRealPrices.length - 1] = liveSpotPrice.value;
    tickLayaPrices[tickLayaPrices.length - 1] = layaPredictedPrice.value;
    tickDiffs[tickDiffs.length - 1] = +(layaPredictedPrice.value - liveSpotPrice.value).toFixed(2);
    if (tickBuyersPct.length > 0) {
      tickBuyersPct[tickBuyersPct.length - 1] = currentBuyersPct.value;
      tickSellersPct[tickSellersPct.length - 1] = currentSellersPct.value;
    }
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
  const vShort = npClip(pNow - p3, -10.0, 10.0);
  const vMed = npClip(pNow - p10, -16.0, 16.0);
  const distFromBeat = pNow - priceToBeat.value;
  const distClamp = npClip(distFromBeat, -18.0, 18.0);

  let sumSq = 0;
  for (let i = 1; i < n; i++) {
    const d = tickRealPrices[i] - tickRealPrices[i - 1];
    sumSq += d * d;
  }
  const tickStd = Math.sqrt(sumSq / n) || 2.5;

  const rawDelta = npClip(0.42 * vShort + 0.22 * vMed + 0.06 * distClamp, -8.0, 8.0);
  const rawTargetLaya = pNow + rawDelta;
  layaPredictedPrice.value = +(
    layaPredictedPrice.value > 1000
      ? 0.80 * layaPredictedPrice.value + 0.20 * rawTargetLaya
      : rawTargetLaya
  ).toFixed(2);

  layaTrend.value = layaPredictedPrice.value >= priceToBeat.value ? 'UP' : 'DOWN';

  const zSignal = Math.abs(layaPredictedPrice.value - priceToBeat.value) / Math.max(4.0, tickStd * 2.2);
  const rawConf = 1.0 / (1.0 + Math.exp(-(0.35 + 1.15 * zSignal)));
  layaConfidence.value = Math.min(0.965, Math.max(0.51, rawConf));
  layaBoolean.value = layaConfidence.value >= layaOptimalThreshold.value;

  const probUp = npClip(0.5 + (distFromBeat / Math.max(18.0, tickStd * 5.0)) * 0.38, 0.06, 0.94);
  currentUpCents.value = Math.round(probUp * 100);
  currentDownCents.value = Math.max(1, 101 - currentUpCents.value);

  // Punto 1 (Modelo Calibrado) & Punto 2 (Riesgo Determinista & Kelly)
  point1ModelConfPct.value = +npClip(0.55 * lastSyncCalibPct.value + 0.45 * (layaConfidence.value * 100.0), 0.0, 99.5).toFixed(1);
  const targetCents = layaTrend.value === 'UP' ? currentUpCents.value : currentDownCents.value;
  const askProbEst = Math.min(0.98, Math.max(0.05, (targetCents + 1) / 100.0));
  const bOdds = Math.max(0.25, (1.0 - askProbEst) / askProbEst);
  const kellyRaw = Math.max(0.0, (layaConfidence.value * bOdds - (1.0 - layaConfidence.value)) / bOdds);
  const marginPts = virtualBankroll.value >= 10.0 ? 30.0 : (virtualBankroll.value >= 1.0 ? 15.0 : 0.0);
  const edgePts = kellyRaw > 0 ? Math.min(1.0, kellyRaw / 0.28) * 40.0 : 0.0;
  point2RiskConfPct.value = +npClip(marginPts + 30.0 + edgePts, 0.0, 99.5).toFixed(1);
  dual85Passed.value = point1ModelConfPct.value > 85.0 && point2RiskConfPct.value > 85.0;

  const localMomBuyers = 50.0 + npClip(((vShort * 2.2 + vMed * 0.9) / Math.max(1.5, tickStd)) * 16.0, -32.0, 32.0);
  currentBuyersPct.value = +npClip(0.65 * localMomBuyers + 0.35 * lastSyncBuyersPct, 5.0, 95.0).toFixed(1);
  currentSellersPct.value = +(100.0 - currentBuyersPct.value).toFixed(1);

  if (
    !isLastMinuteLocked.value &&
    dual85Passed.value &&
    !activeVirtualBet.value &&
    currentWindowStartBucket.value !== 0 &&
    autoOperatedWindowBucket !== currentWindowStartBucket.value &&
    virtualBankroll.value >= 1.0
  ) {
    autoOperatedWindowBucket = currentWindowStartBucket.value;
    openVirtualBet('kelly');
  }

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

  if (isLastMinuteLocked.value || remainingWindowSec.value < 60) {
    helperNotice.value = `<span style="color:#fca5a5;font-weight:700;">🔒 Último minuto (${remainingWindowSec.value}s restantes): las apuestas están deshabilitadas hasta que inicie el siguiente periodo de 5m.</span>`;
    return;
  }

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

  if (!isEarlyCashout && !isLastMinuteLocked.value && autoBet.value) {
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
  remainingWindowSec.value = remSec;

  const bucketNow = Math.floor((atomicNowMs + windowOffsetSec.value * 1000) / 300000);
  if (currentWindowStartBucket.value !== 0 && bucketNow !== currentWindowStartBucket.value) {
    currentWindowStartBucket.value = bucketNow;
    autoOperatedWindowBucket = 0;
    isLastMinuteLocked.value = false;
    if (activeVirtualBet.value) {
      settleVirtualBet(false);
    }
    officialPolyPriceToBeat.value = null;
    if (!manualBeatVal.value) {
      priceToBeat.value = liveSpotPrice.value || priceToBeat.value;
    }
    helperNotice.value =
      '🔓 <strong>Nuevo periodo de 5 minutos iniciado:</strong> Apuestas rehabilitadas automáticamente. Esperando señal dual &gt;85% (Punto 1 + Punto 2).';
    syncPolymarket5mContract();
  }

  const nextLock = remSec < 60;
  if (nextLock !== isLastMinuteLocked.value) {
    isLastMinuteLocked.value = nextLock;
    helperNotice.value = nextLock
      ? '🔒 <strong>Último minuto (&lt;60s) de la ventana 5m:</strong> Las apuestas han sido deshabilitadas temporalmente y se reiniciarán en cuanto empiece el siguiente periodo.'
      : '🔓 <strong>Apuestas rehabilitadas:</strong> Nuevo periodo 5m activo (esperando Punto 1 &gt;85% y Punto 2 &gt;85%).';
  }

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

const polymarketExactCanvasPlugin = {
  id: 'polymarketExactCanvasPlugin',
  afterDatasetsDraw(chart: Chart) {
    const { ctx, chartArea, scales } = chart;
    if (!chartArea || !scales || !scales.y) return;
    const yScale = scales.y;
    const xScale = scales.x;
    const { left, right, top, bottom } = chartArea;
    const isLight = polyThemeMode.value === 'light';

    const drawChevronTag = (
      yPx: number,
      bg: string,
      txt: string,
      opts?: { sharpLeft?: boolean }
    ) => {
      ctx.save();
      ctx.font = 'bold 10.5px Inter, sans-serif';
      const w = ctx.measureText(txt).width + 16;
      const h = 20;
      const tip = opts?.sharpLeft ? 7 : 4;
      const xStart = right - 2;
      ctx.fillStyle = bg;
      ctx.beginPath();
      if (opts?.sharpLeft) {
        ctx.moveTo(xStart, yPx);
        ctx.lineTo(xStart + tip, yPx - h / 2);
        ctx.lineTo(xStart + w + tip, yPx - h / 2);
        ctx.lineTo(xStart + w + tip, yPx + h / 2);
        ctx.lineTo(xStart + tip, yPx + h / 2);
        ctx.closePath();
      } else {
        const r = 5;
        const x0 = xStart + 4;
        const y0 = yPx - h / 2;
        const rw = w + 2;
        ctx.moveTo(x0 + r, y0);
        ctx.lineTo(x0 + rw - r, y0);
        ctx.quadraticCurveTo(x0 + rw, y0, x0 + rw, y0 + r);
        ctx.lineTo(x0 + rw, y0 + h - r);
        ctx.quadraticCurveTo(x0 + rw, y0 + h, x0 + rw - r, y0 + h);
        ctx.lineTo(x0 + r, y0 + h);
        ctx.quadraticCurveTo(x0, y0 + h, x0, y0 + h - r);
        ctx.lineTo(x0, y0 + r);
        ctx.quadraticCurveTo(x0, y0, x0 + r, y0);
        ctx.closePath();
      }
      ctx.fill();
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(txt, xStart + tip + w / 2, yPx + 0.5);
      ctx.restore();
    };

    const drawDashLine = (yPx: number, stroke: string) => {
      ctx.save();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 1.25;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(left, yPx);
      ctx.lineTo(right, yPx);
      ctx.stroke();
      ctx.restore();
    };

    // Línea punteada naranja de precio vivo
    const spotVal = displaySpotPrice || liveSpotPrice.value;
    if (spotVal > 0) {
      const ySpot = Math.max(top + 6, Math.min(bottom - 6, yScale.getPixelForValue(spotVal)));
      drawDashLine(ySpot, 'rgba(245, 158, 11, 0.55)');
    }

    // Target (Price To Beat) inteligente: Target ↑ / Target ↓ / < Target
    const targetVal = priceToBeat.value;
    if (targetVal > 0) {
      if (targetVal > yScale.max) {
        drawDashLine(top + 2, 'rgba(148, 163, 184, 0.6)');
        drawChevronTag(top + 12, '#64748b', 'Target ↑');
      } else if (targetVal < yScale.min) {
        drawDashLine(bottom - 2, 'rgba(148, 163, 184, 0.6)');
        drawChevronTag(bottom - 12, '#64748b', 'Target ↓');
      } else {
        const yTarget = Math.max(top + 10, Math.min(bottom - 10, yScale.getPixelForValue(targetVal)));
        drawDashLine(yTarget, 'rgba(148, 163, 184, 0.72)');
        drawChevronTag(yTarget, '#8b95a5', 'Target', { sharpLeft: true });
      }
    }

    // Línea superpuesta + etiqueta Laya
    const layaVal = displayLayaPrice || layaPredictedPrice.value;
    if (layaVal > 0) {
      const yLaya = Math.max(top + 10, Math.min(bottom - 10, yScale.getPixelForValue(layaVal)));
      drawDashLine(yLaya, 'rgba(168, 85, 247, 0.35)');
      drawChevronTag(yLaya, '#9333ea', 'Laya', { sharpLeft: true });
    }

    // Punto pulsante en la punta de la serie en vivo
    const meta0 = chart.getDatasetMeta(0);
    if (meta0 && meta0.data && meta0.data.length > 0) {
      const tipPt = meta0.data[meta0.data.length - 1];
      if (tipPt && !isNaN(tipPt.x) && !isNaN(tipPt.y)) {
        const pulse = 0.5 + 0.5 * Math.sin(performance.now() * 0.008);
        ctx.save();
        ctx.fillStyle = `rgba(245, 158, 11, ${0.18 + pulse * 0.18})`;
        ctx.beginPath();
        ctx.arc(tipPt.x, tipPt.y, 7 + pulse * 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#f59e0b';
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.arc(tipPt.x, tipPt.y, 4.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
      }
    }

    // Crosshair vertical y Tooltip pill estilo Polymarket al hacer hover
    if (chartHoverX !== null && chartHoverX >= left && chartHoverX <= right && xScale) {
      const hoverTs = xScale.getValueForPixel(chartHoverX);
      const ds0 = (chart.data.datasets[0]?.data || []) as Array<{ x: number; y: number }>;
      const ds1 = (chart.data.datasets[1]?.data || []) as Array<{ x: number; y: number }>;
      let nearSpot: { x: number; y: number } | null = null;
      let minDist = Infinity;
      for (let i = 0; i < ds0.length; i++) {
        const d = Math.abs(ds0[i].x - hoverTs);
        if (d < minDist) {
          minDist = d;
          nearSpot = ds0[i];
        }
      }
      let nearLaya: { x: number; y: number } | null = null;
      let minDistL = Infinity;
      for (let i = 0; i < ds1.length; i++) {
        const d = Math.abs(ds1[i].x - hoverTs);
        if (d < minDistL) {
          minDistL = d;
          nearLaya = ds1[i];
        }
      }

      if (nearSpot) {
        const pxX = xScale.getPixelForValue(nearSpot.x);
        const pxY = yScale.getPixelForValue(nearSpot.y);

        ctx.save();
        ctx.strokeStyle = isLight ? 'rgba(100, 116, 139, 0.35)' : 'rgba(148, 163, 184, 0.35)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pxX, top);
        ctx.lineTo(pxX, bottom);
        ctx.stroke();

        ctx.fillStyle = '#f59e0b';
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(pxX, pxY, 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        const priceLine = `$${Number(nearSpot.y).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        const layaLine = nearLaya
          ? `Laya: $${Number(nearLaya.y).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
          : '';
        const dtStr = new Date(nearSpot.x).toLocaleString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
          second: '2-digit',
          hour12: true,
        });

        ctx.font = 'bold 12px Inter, sans-serif';
        const w1 = ctx.measureText(priceLine).width + 20;
        ctx.font = '600 11px Inter, sans-serif';
        const w2 = layaLine ? ctx.measureText(layaLine).width + 16 : 0;
        const w3 = ctx.measureText(dtStr).width + 16;
        const boxW = Math.max(w1, w2, w3, 152);
        const boxH = layaLine ? 60 : 44;
        let boxX = pxX + 12;
        if (boxX + boxW > right) boxX = pxX - boxW - 12;
        boxX = Math.max(left + 4, boxX);
        const boxY = Math.max(top + 6, Math.min(bottom - boxH - 6, pxY - boxH / 2));

        ctx.fillStyle = isLight ? 'rgba(255, 255, 255, 0.96)' : 'rgba(15, 23, 42, 0.95)';
        ctx.strokeStyle = isLight ? 'rgba(203, 213, 225, 0.95)' : 'rgba(51, 65, 85, 0.95)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(boxX, boxY, boxW, boxH, 8);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#f59e0b';
        ctx.beginPath();
        ctx.arc(boxX + 12, boxY + 15, 3.5, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = isLight ? '#0f172a' : '#f8fafc';
        ctx.font = 'bold 12px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(priceLine, boxX + 21, boxY + 15);

        if (layaLine) {
          ctx.fillStyle = isLight ? '#7e22ce' : '#c084fc';
          ctx.font = '600 11px Inter, sans-serif';
          ctx.fillText(layaLine, boxX + 10, boxY + 32);
        }

        ctx.fillStyle = isLight ? '#64748b' : '#94a3b8';
        ctx.font = '600 10.5px Inter, sans-serif';
        ctx.fillText(dtStr, boxX + 10, boxY + (layaLine ? 48 : 32));
        ctx.restore();
      }
    }
  },
};

function renderFluidOverlay60FPS() {
  const overlayEl = overlayChartCanvas.value;
  if (!overlayEl || !liveSpotPrice.value) {
    requestAnimationFrame(renderFluidOverlay60FPS);
    return;
  }

  const nowMs = feedManager.getAtomicNowMs();
  if (!stage1Spot) stage1Spot = liveSpotPrice.value;
  if (!displaySpotPrice) displaySpotPrice = liveSpotPrice.value;
  if (!stage1Laya) stage1Laya = layaPredictedPrice.value || liveSpotPrice.value;
  if (!displayLayaPrice) displayLayaPrice = layaPredictedPrice.value || liveSpotPrice.value;

  const microWave = Math.sin(nowMs * 0.0082) * 0.20 + Math.cos(nowMs * 0.0051) * 0.11;
  stage1Spot += (liveSpotPrice.value - stage1Spot) * 0.18;
  displaySpotPrice += (stage1Spot + microWave - displaySpotPrice) * 0.16;

  const targetLaya = layaPredictedPrice.value || liveSpotPrice.value;
  stage1Laya += (targetLaya - stage1Laya) * 0.15;
  displayLayaPrice += (stage1Laya + microWave * 0.55 - displayLayaPrice) * 0.14;

  if (nowMs - lastFluidSampleMs >= FLUID_SAMPLE_MS) {
    lastFluidSampleMs = nowMs;
    fluidPoints.push({
      ts: nowMs,
      real: +displaySpotPrice.toFixed(2),
      laya: +displayLayaPrice.toFixed(2),
    });
    const cutoff = nowMs - FLUID_WINDOW_MS - 8000;
    while (fluidPoints.length > 10 && fluidPoints[0].ts < cutoff) {
      fluidPoints.shift();
    }
  }

  const xMin = nowMs - FLUID_WINDOW_MS;
  const xMax = nowMs + FLUID_LEAD_MS;

  const realData = fluidPoints.map((p) => ({ x: p.ts, y: p.real }));
  realData.push({ x: nowMs, y: +displaySpotPrice.toFixed(2) });

  const stepDelta = (displayLayaPrice - displaySpotPrice) / 3.0;
  const layaData = fluidPoints.map((p) => ({ x: p.ts, y: p.laya }));
  layaData.push({ x: nowMs, y: +displayLayaPrice.toFixed(2) });
  layaData.push({ x: nowMs + 1000, y: +(displaySpotPrice + stepDelta).toFixed(2) });
  layaData.push({ x: nowMs + 2000, y: +(displaySpotPrice + stepDelta * 2).toFixed(2) });
  layaData.push({ x: nowMs + 3000, y: +displayLayaPrice.toFixed(2) });

  let rMin = Infinity;
  let rMax = -Infinity;
  for (let i = 0; i < realData.length; i++) {
    if (realData[i].x >= xMin) {
      if (realData[i].y < rMin) rMin = realData[i].y;
      if (realData[i].y > rMax) rMax = realData[i].y;
    }
  }
  if (!isFinite(rMin) || !isFinite(rMax)) {
    rMin = displaySpotPrice - 12;
    rMax = displaySpotPrice + 12;
  }
  let vMin = rMin;
  let vMax = rMax;
  for (let i = 0; i < layaData.length; i++) {
    if (layaData[i].x >= xMin) {
      const ly = Math.max(rMin - 9.0, Math.min(rMax + 9.0, layaData[i].y));
      if (ly < vMin) vMin = ly;
      if (ly > vMax) vMax = ly;
    }
  }
  if (priceToBeat.value > 0 && Math.abs(priceToBeat.value - displaySpotPrice) <= 22.0) {
    if (priceToBeat.value < vMin) vMin = priceToBeat.value;
    if (priceToBeat.value > vMax) vMax = priceToBeat.value;
  }

  const rawSpan = Math.max(28.0, Math.min(65.0, vMax - vMin));
  const pad = Math.max(7.0, rawSpan * 0.28);
  const targetYMin = vMin - pad;
  const targetYMax = vMax + pad;
  if (!smoothYMin || !smoothYMax) {
    smoothYMin = targetYMin;
    smoothYMax = targetYMax;
  } else {
    smoothYMin += (targetYMin - smoothYMin) * 0.12;
    smoothYMax += (targetYMax - smoothYMax) * 0.12;
  }
  const yStep = smoothYMax - smoothYMin <= 80 ? 10 : 20;

  const isLight = polyThemeMode.value === 'light';
  const gridColor = isLight ? 'rgba(148, 163, 184, 0.22)' : 'rgba(255, 255, 255, 0.06)';
  const tickColor = isLight ? '#64748b' : '#94a3b8';
  const ctx1 = overlayEl.getContext('2d');

  if (ctx1) {
    if (!overlayChartInstance) {
      const grad = ctx1.createLinearGradient(0, 0, 0, 340);
      grad.addColorStop(0, isLight ? 'rgba(245, 158, 11, 0.14)' : 'rgba(247, 147, 26, 0.22)');
      grad.addColorStop(1, 'rgba(245, 158, 11, 0.0)');

      overlayChartInstance = new Chart(ctx1, {
        type: 'line',
        data: {
          datasets: [
            {
              label: 'Polymarket BTC Live ($)',
              data: realData as any,
              borderColor: '#f59e0b',
              backgroundColor: grad,
              fill: true,
              borderWidth: 2.5,
              cubicInterpolationMode: 'monotone',
              tension: 0.4,
              pointRadius: 0,
            },
            {
              label: 'Trazo Modelo Laya ($)',
              data: layaData as any,
              borderColor: '#a855f7',
              backgroundColor: 'transparent',
              borderWidth: 2.0,
              borderDash: [5, 4],
              cubicInterpolationMode: 'monotone',
              tension: 0.4,
              pointRadius: (c: any) => (c.dataIndex === layaData.length - 1 ? 4.5 : 0),
              pointBackgroundColor: '#a855f7',
              pointBorderColor: '#ffffff',
              pointBorderWidth: 1.5,
            },
          ],
        },
        plugins: [polymarketExactCanvasPlugin],
        options: {
          animation: false,
          parsing: false,
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { right: 64, top: 10, bottom: 6 } },
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: {
            x: {
              type: 'linear',
              min: xMin,
              max: xMax,
              grid: { display: false },
              border: { display: false },
              afterBuildTicks(axis: any) {
                const ticks: Array<{ value: number }> = [];
                const step = 4000;
                const first = Math.ceil((axis.min + 3600) / step) * step;
                for (let t = first; t <= axis.max - 1500; t += step) {
                  ticks.push({ value: t });
                }
                axis.ticks = ticks;
              },
              ticks: {
                color: tickColor,
                font: { size: 11, weight: 'bold' },
                callback: (val: any) =>
                  new Date(Number(val)).toLocaleTimeString('en-US', {
                    hour12: true,
                    hour: 'numeric',
                    minute: '2-digit',
                    second: '2-digit',
                  }),
              },
            },
            y: {
              position: 'right',
              min: smoothYMin,
              max: smoothYMax,
              grid: { color: gridColor },
              border: { display: false },
              ticks: {
                color: tickColor,
                stepSize: yStep,
                maxTicksLimit: 6,
                font: { size: 11, weight: 'bold' },
                callback: (v: any) =>
                  `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`,
              },
            },
          },
        },
      });
    } else {
      const scalesAny = overlayChartInstance.options.scales as any;
      scalesAny.x.min = xMin;
      scalesAny.x.max = xMax;
      scalesAny.y.min = smoothYMin;
      scalesAny.y.max = smoothYMax;
      scalesAny.y.ticks.stepSize = yStep;
      overlayChartInstance.data.datasets[0].data = realData as any;
      overlayChartInstance.data.datasets[1].data = layaData as any;
      overlayChartInstance.update('none');
    }
  }

  requestAnimationFrame(renderFluidOverlay60FPS);
}

function renderRealtimeCharts() {
  if (tickLabels.length < 2 || !diffChartCanvas.value) return;

  if (buyersSellersChartCanvas.value && tickBuyersPct.length >= 2) {
    const ctxBS = buyersSellersChartCanvas.value.getContext('2d');
    const eq50 = tickLabels.map(() => 50);
    if (ctxBS) {
      if (!buyersSellersChartInstance) {
        buyersSellersChartInstance = new Chart(ctxBS, {
          type: 'line',
          data: {
            labels: tickLabels,
            datasets: [
              { label: '% Compradores', data: tickBuyersPct, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.14)', fill: true, borderWidth: 2, tension: 0.28, pointRadius: 0 },
              { label: '% Vendedores', data: tickSellersPct, borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.08)', fill: true, borderWidth: 2, tension: 0.28, pointRadius: 0 },
              { label: 'Equilibrio 50%', data: eq50, borderColor: 'rgba(148, 163, 184, 0.45)', borderDash: [4, 4], borderWidth: 1.2, pointRadius: 0, fill: false },
            ],
          },
          options: {
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: { display: false },
              y: { min: 0, max: 100, ticks: { color: '#94a3b8', stepSize: 25, callback: (v) => `${v}%` } },
            },
          },
        });
      } else {
        buyersSellersChartInstance.data.labels = tickLabels;
        buyersSellersChartInstance.data.datasets[0].data = tickBuyersPct;
        buyersSellersChartInstance.data.datasets[1].data = tickSellersPct;
        buyersSellersChartInstance.data.datasets[2].data = eq50;
        buyersSellersChartInstance.update('none');
      }
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
      lastSyncCalibPct.value = Number(latestRl.value.calibration_index_pct);
      kpiCalibSub.value = `Fiabilidad RL Local (1 − Brier): ${latestRl.value.calibration_index_pct.toFixed(1)}% (${latestRl.value.episodes_trained} ep)`;
    }
    if (data.summary?.buyers_pct !== undefined) {
      lastSyncBuyersPct = Number(data.summary.buyers_pct);
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
  if (overlayChartCanvas.value) {
    overlayChartCanvas.value.addEventListener('mousemove', (e: MouseEvent) => {
      const rect = overlayChartCanvas.value!.getBoundingClientRect();
      chartHoverX = e.clientX - rect.left;
      chartHoverY = e.clientY - rect.top;
    });
    overlayChartCanvas.value.addEventListener('mouseleave', () => {
      chartHoverX = null;
      chartHoverY = null;
    });
  }
  initInitialPriceHistory();
  feedManager.startAllStreams();
  requestAnimationFrame(updateCountdownClock);
  requestAnimationFrame(renderFluidOverlay60FPS);
  syncAgentsBackground('/api/compare');
  setInterval(() => syncAgentsBackground('/api/compare'), 3500);
  setInterval(syncPolymarket5mContract, 1200);
  setInterval(() => feedManager.syncAtomicClock(), 10000);
});
</script>

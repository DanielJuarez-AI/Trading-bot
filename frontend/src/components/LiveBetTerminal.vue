<template>
  <section class="live-bet-terminal">
    <div class="bet-header">
      <div>
        <h2>
          🎰 Simulador de Apuestas en Tiempo Real (Dinero Ficticio &bull; Polymarket &amp; MEXC 5m)
          <span class="latency-pill">{{ latencyText }}</span>
        </h2>
        <p style="font-size: 0.75rem; color: #94a3b8; margin-top: 2px" v-html="helperNotice"></p>
      </div>
      <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap">
        <button
          class="btn-start-bet"
          :style="{
            background: activeBet
              ? 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)'
              : 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          }"
          @click="emit('open-bet', 'kelly_main_btn')"
        >
          <span v-if="!activeBet">▶ INICIAR APUESTA AHORA (Kelly Laya)</span>
          <span v-else>⏳ APUESTA EN JUEGO ({{ activeBet.direction }} ${{ activeBet.stake_usd.toFixed(2) }})</span>
        </button>

        <label class="auto-bet-label">
          <input type="checkbox" :checked="autoBet" @change="emit('toggle-auto', ($event.target as HTMLInputElement).checked)" />
          Piloto Automático Laya (Continuo)
        </label>

        <button class="btn-cashout" @click="emit('cashout')">⚡ Vender Posición (Cashout CLOB)</button>
        <button class="btn-reset" @click="emit('reset-bankroll')">🔄 Reset ($1,000)</button>
      </div>
    </div>

    <div class="bet-grid">
      <!-- Sub-panel 1: Controles Up / Down + One-Tap Buy -->
      <div class="sub-box">
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center">
            <span style="font-size: 0.8rem; font-weight: 700; color: #e2e8f0">Seleccionar Dirección (1-Tap Buy)</span>
            <span
              style="font-size: 0.78rem; font-weight: 800"
              :style="{ color: layaTrend === 'UP' ? '#10b981' : '#ef4444' }"
            >
              Tendencia Laya: COMPRA {{ layaTrend }} {{ layaTrend === 'UP' ? '▲' : '▼' }} ({{ (layaConfidence * 100).toFixed(1) }}%)
            </span>
          </div>

          <div class="up-down-buttons">
            <button
              class="btn-outcome"
              :class="{ 'active-up': selectedDirection === 'UP' }"
              @click="emit('select-direction', 'UP')"
            >
              <span v-if="layaTrend === 'UP'" class="laya-rec-tag">★ LAYA</span>
              Up <span>{{ upCents }}¢</span>
            </button>
            <button
              class="btn-outcome"
              :class="{ 'active-down': selectedDirection === 'DOWN' }"
              @click="emit('select-direction', 'DOWN')"
            >
              <span v-if="layaTrend === 'DOWN'" class="laya-rec-tag">★ LAYA</span>
              Down <span>{{ downCents }}¢</span>
            </button>
          </div>
        </div>

        <div>
          <div style="font-size: 0.72rem; color: var(--text-muted); margin-bottom: 6px; text-transform: uppercase">
            One-Tap Buy con Dinero Ficticio (Descuenta de Caja Real)
          </div>
          <div class="one-tap-grid">
            <div class="tap-card" @click="emit('open-bet', '5')">
              <div class="tap-amount">$5</div>
              <div class="tap-win">win <strong>${{ (5 / askProb).toFixed(2) }}</strong></div>
            </div>
            <div class="tap-card" @click="emit('open-bet', '25')">
              <div class="tap-amount">$25</div>
              <div class="tap-win">win <strong>${{ (25 / askProb).toFixed(2) }}</strong></div>
            </div>
            <div class="tap-card" @click="emit('open-bet', '100')">
              <div class="tap-amount">$100</div>
              <div class="tap-win">win <strong>${{ (100 / askProb).toFixed(2) }}</strong></div>
            </div>
            <div class="tap-card" style="border-color: var(--laya-purple)" @click="emit('open-bet', 'kelly')">
              <div class="tap-amount" style="color: var(--laya-purple)">Kelly</div>
              <div class="tap-win">Auto <strong>Laya</strong></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sub-panel 2: Estado del Ticket Activo y Banca Ficticia -->
      <div class="sub-box">
        <div class="ticket-stats">
          <div class="t-stat">
            <div class="t-stat-label">Banca Ficticia Disponible</div>
            <div class="t-stat-val" style="color: var(--true-green)">${{ virtualBankroll.toFixed(2) }}</div>
          </div>
          <div class="t-stat">
            <div class="t-stat-label">Apuesta Activa (Shares)</div>
            <div class="t-stat-val" style="color: var(--rl-gold)">
              {{ activeBet ? `$${activeBet.stake_usd.toFixed(2)} (${activeBet.shares.toFixed(1)} sh @ ${activeBet.entry_ask_cents}¢)` : '$0.00 (Sin apuesta)' }}
            </div>
          </div>
          <div class="t-stat">
            <div class="t-stat-label">BTC Entrada &rarr; Actual</div>
            <div class="t-stat-val">
              {{ activeBet ? `$${activeBet.entry_btc.toLocaleString()} → $${liveSpotPrice.toLocaleString()}` : `$-- → $${liveSpotPrice.toLocaleString()}` }}
            </div>
          </div>
          <div class="t-stat">
            <div class="t-stat-label">Récord Sesión (Ganadas/Perdidas)</div>
            <div class="t-stat-val">{{ sessionWins }}W / {{ sessionLosses }}L</div>
          </div>
        </div>

        <div class="floating-pnl-box">
          <div>
            <div class="t-stat-label">PnL No Realizado (Mark-to-Market en Vivo)</div>
            <div style="font-size: 0.74rem; color: var(--text-muted)">
              <template v-if="activeBet">
                {{
                  activeBet.winning_now
                    ? `🟢 Ganando frente a Price To Beat: Si cierra así al 00:00 cobras $${activeBet.shares.toFixed(2)}`
                    : `🔴 Debajo de la meta ($${priceToBeat.toFixed(2)}): Si cierra así al 00:00 expira en $0.00`
                }}
              </template>
              <template v-else>
                Haz clic en "▶ INICIAR APUESTA AHORA" o en $5 / $25 / $100 para entrar en esta vela de 5m.
              </template>
            </div>
          </div>
          <div
            style="font-size: 1.35rem; font-weight: 800; font-family: Consolas, monospace"
            :class="activeBet && activeBet.floating_pnl < 0 ? 'diff-negative' : 'diff-positive'"
          >
            {{
              activeBet
                ? `${activeBet.floating_pnl >= 0 ? '+' : ''}$${activeBet.floating_pnl.toFixed(2)} (${activeBet.floating_roi >= 0 ? '+' : ''}${activeBet.floating_roi.toFixed(2)}%)`
                : '+$0.00 (0.00%)'
            }}
          </div>
        </div>
      </div>

      <!-- Sub-panel 3: Curva de Capital Ficticio -->
      <div class="sub-box">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px">
          <span style="font-size: 0.75rem; font-weight: 700; color: #e2e8f0; text-transform: uppercase">Curva de Capital ($ USD)</span>
          <span style="font-size: 0.75rem; font-weight: 700; color: var(--true-green)">
            Banca: ${{ virtualBankroll.toFixed(2) }} ({{ roiTotalPct >= 0 ? '+' : '' }}{{ roiTotalPct.toFixed(2) }}%)
          </span>
        </div>
        <div style="position: relative; height: 135px; width: 100%">
          <slot name="equity-chart"></slot>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ActiveVirtualBet, TrendDirection } from '../types/trading';

const props = defineProps<{
  latencyText: string;
  helperNotice: string;
  activeBet: ActiveVirtualBet | null;
  autoBet: boolean;
  layaTrend: TrendDirection;
  layaConfidence: number;
  selectedDirection: TrendDirection;
  upCents: number;
  downCents: number;
  virtualBankroll: number;
  liveSpotPrice: number;
  priceToBeat: number;
  sessionWins: number;
  sessionLosses: number;
}>();

const emit = defineEmits<{
  (e: 'open-bet', mode: string): void;
  (e: 'toggle-auto', val: boolean): void;
  (e: 'cashout'): void;
  (e: 'reset-bankroll'): void;
  (e: 'select-direction', dir: TrendDirection): void;
}>();

const askProb = computed(() => {
  const c = props.selectedDirection === 'UP' ? props.upCents : props.downCents;
  return Math.max(0.05, Math.min(0.98, (c + 1) / 100.0));
});

const roiTotalPct = computed(() => ((props.virtualBankroll - 1000.0) / 1000.0) * 100.0);
</script>

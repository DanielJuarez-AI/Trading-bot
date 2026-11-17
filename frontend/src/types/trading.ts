export type OracleSource = 'polymarket_rtds' | 'mexc' | 'coinbase' | 'binance';
export type TrendDirection = 'UP' | 'DOWN';

export interface ActiveVirtualBet {
  id: string;
  opened_at: string;
  direction: TrendDirection;
  entry_ask_cents: number;
  current_bid_cents: number;
  entry_btc: number;
  stake_usd: number;
  shares: number;
  mark_value_usd: number;
  floating_pnl: number;
  floating_roi: number;
  winning_now: boolean;
}

export interface VirtualTradeRecord {
  id: string;
  time: string;
  direction: TrendDirection;
  btc_move: string;
  conf: string;
  stake: number;
  outcome: string;
  roi: number;
  pnl: number;
  bankroll: number;
}

export interface AgentMessage {
  id: string;
  time: string;
  from: string;
  to: string;
  summary: string;
}

export interface MultiAgentPayload {
  agents?: {
    scout?: { regime: string; liquidity_score: number };
    trainer?: { episodes_trained: number };
    risk?: { stake_usd: number; kelly_fraction_pct: number; approved_boolean: boolean };
    auditor?: { status: string };
  };
  message_bus?: AgentMessage[];
}

export interface RlMetricsPayload {
  episodes_trained: number;
  total_rl_steps: number;
  optimal_threshold: number;
  calibration_index_pct: number;
  win_rate_pct: number;
  reward_history: number[];
  calibration_history: number[];
}

export interface Poly5mSyncResponse {
  ts: number;
  window_ts: number;
  slug: string;
  title: string;
  price_to_beat: number | null;
  up_token_id: string;
  down_token_id: string;
  up_cents: number;
  down_cents: number;
  end_date: string;
  atomic_server_ms: number;
  pc_clock_drift_sec: number;
}

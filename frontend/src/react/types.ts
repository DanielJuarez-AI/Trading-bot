export type AgentRunStatus = 'RUNNING' | 'PAUSED' | 'STOPPED';
export type AgentActionType = 'BUY' | 'HOLD' | 'SELL';
export type ExecutionMode = 'LIVE' | 'REPLAY';

export interface ContractIndicators {
  parkinson_vol_5m: number;
  garman_klass_vol_5m: number;
  realized_vol_5m: number;
  log_return_5m: number;
  volume_zscore_5m: number;
  taker_buy_ratio_5m: number;
  polymarket_clob_mid: number;
  polymarket_momentum_5m: number;
}

export interface LlmProposal {
  action: AgentActionType;
  symbol: string;
  candle_date: string;
  justification: string;
}

export interface AgentPortfolioState {
  status: AgentRunStatus;
  symbol: string;
  cash_usdc: number;
  position_shares: number;
  avg_entry_prob: number;
  last_mark_prob: number;
  position_value_usdc: number;
  total_equity_usdc: number;
  net_pnl_usdc: number;
  net_return_pct: number;
  exposure_pct: number;
  realized_pnl_usdc: number;
  daily_pnl_usdc: number;
  peak_equity_usdc: number;
  max_drawdown_pct: number;
  last_candle_ts: number;
  last_candle_iso: string;
  total_cycles: number;
  executed_orders_count: number;
  rejected_orders_count: number;
  restart_recoveries: number;
  updated_at: string;
}

export interface StrategyMetrics {
  strategy: string;
  initial_capital_usdc: number;
  final_equity_usdc: number;
  net_return_usdc: number;
  net_return_pct: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  operations_count: number;
  rejected_actions: number;
  mean_latency_ms: number;
  equity_curve: number[];
}

export interface ErrorScenarioResult {
  scenario_code: string;
  handled_correctly: boolean;
  agent_response: string;
  message: string;
  retries_attempted?: number;
  backoff_schedule?: string;
}

export interface DecisionRecord {
  decision_id: number;
  cycle_num: number;
  mode: ExecutionMode;
  symbol: string;
  candle_timestamp: number;
  candle_iso: string;
  data_age_sec: number;
  btc_close: number;
  poly_clob_prob: number;
  model_forecast_prob: number;
  model_forecast_btc: number;
  model_signal: AgentActionType;
  indicators: ContractIndicators;
  llm_model: string;
  llm_version: string;
  llm_hardware: string;
  llm_latency_ms: number;
  llm_action: AgentActionType;
  llm_justification: string;
  llm_raw_json: string;
  risk_approved: number;
  risk_status: string;
  risk_reason: string;
  final_action: AgentActionType;
  cash_after_usdc: number;
  position_shares_after: number;
  equity_after_usdc: number;
  created_at: string;
}

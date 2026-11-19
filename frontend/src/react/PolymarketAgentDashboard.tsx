import React, { useEffect, useState } from 'react';
import type {
  AgentPortfolioState,
  DecisionRecord,
  ErrorScenarioResult,
  StrategyMetrics,
} from './types';

export const PolymarketAgentDashboard: React.FC = () => {
  const [agentState, setAgentState] = useState<AgentPortfolioState | null>(null);
  const [windowTiming, setWindowTiming] = useState<any>(null);
  const [latestCycle, setLatestCycle] = useState<any>(null);
  const [llmConfig, setLlmConfig] = useState<any>(null);
  const [riskConfig, setRiskConfig] = useState<any>(null);
  const [comparison, setComparison] = useState<any>(null);
  const [liveDecisions, setLiveDecisions] = useState<DecisionRecord[]>([]);
  const [replayDecisions, setReplayDecisions] = useState<DecisionRecord[]>([]);
  const [errorLogs, setErrorLogs] = useState<any[]>([]);
  const [errorSuite, setErrorSuite] = useState<ErrorScenarioResult[]>([]);
  const [decisionTab, setDecisionTab] = useState<'REPLAY' | 'LIVE'>('REPLAY');
  const [bannerMsg, setBannerMsg] = useState<string>('');

  const fetchAgentDashboard = async () => {
    const res = await fetch('/api/final_agent/status', { credentials: 'same-origin' });
    if (!res.ok) return;
    const data = await res.json();
    setAgentState(data.agent_state);
    setWindowTiming(data.window_timing || null);
    setLatestCycle(data.latest_cycle);
    setLlmConfig(data.llm_config);
    setRiskConfig(data.risk_config);
    setComparison(data.strategy_comparison);
    setLiveDecisions(data.recent_decisions_live || []);
    setReplayDecisions(data.recent_decisions_replay || []);
    setErrorLogs(data.recent_error_logs || []);
    if (data.error_suite_summary?.scenarios) {
      setErrorSuite(data.error_suite_summary.scenarios);
    }
  };

  useEffect(() => {
    fetchAgentDashboard();
    const timer = setInterval(fetchAgentDashboard, 4000);
    return () => clearInterval(timer);
  }, []);

  const sendControl = async (action: string, liquidateOnStop = false) => {
    const res = await fetch('/api/final_agent/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ action, liquidate_on_stop: liquidateOnStop }),
    });
    const data = await res.json();
    setBannerMsg(data.message || `Control ejecutado: ${action}`);
    await fetchAgentDashboard();
  };

  const triggerErrorScenario = async (scenarioCode: string) => {
    const res = await fetch('/api/final_agent/trigger_error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ scenario_code: scenarioCode }),
    });
    const data = await res.json();
    setBannerMsg(`[${data.scenario_code}] ${data.message}`);
    await fetchAgentDashboard();
  };

  if (!agentState) {
    return <div>Cargando Agente Financiero Polymarket (React + TypeScript)...</div>;
  }

  const strategies: StrategyMetrics[] = comparison?.strategies
    ? [
        comparison.strategies.model_without_llm,
        comparison.strategies.agent_with_llm,
        comparison.strategies.buy_and_hold,
      ]
    : [];

  return (
    <section className="react-final-agent-panel">
      <header>
        <h2>Agente de IA Financiero Polymarket (React + TypeScript &bull; Ollama Local &bull; Paper $50,000 USDC)</h2>
        <div>
          <span>Activo: {agentState.symbol}</span> | <span>Estado: {agentState.status}</span> |{' '}
          <span>Patrimonio: ${agentState.total_equity_usdc.toLocaleString('en-US', { minimumFractionDigits: 2 })} USDC</span>
        </div>
      </header>

      {bannerMsg && <div className="agent-banner">{bannerMsg}</div>}

      <div className="human-controls">
        <button onClick={() => sendControl('START')}>Iniciar</button>
        <button onClick={() => sendControl('PAUSE')}>Pausar</button>
        <button onClick={() => sendControl('STOP', false)}>Detener (Conservar Posición)</button>
        <button onClick={() => sendControl('STOP', true)}>Detener y Liquidar</button>
      </div>

      <div className="cycle-details">
        <p>Fecha Vela Cerrada: {latestCycle?.candle_iso} (Edad: {latestCycle?.data_age_sec}s)</p>
        <p>
          Pronóstico Laya: {((latestCycle?.forecast?.model_forecast_prob || 0) * 100).toFixed(2)}% |
          Punto 1 (Modelo Calibrado): {(latestCycle?.forecast?.point1_model_confidence_pct || 0).toFixed(1)}% (&gt;85%) |
          Punto 2 (Riesgo &amp; Kelly): {(latestCycle?.forecast?.point2_risk_confidence_pct || 0).toFixed(1)}% (&gt;85%)
        </p>
        <p>
          Ventana 5m: {windowTiming?.remaining_sec ?? '--'}s restantes —{' '}
          {windowTiming?.last_minute_locked ? '🔒 ÚLTIMO MINUTO (<60s): APUESTAS DESHABILITADAS' : '🟢 APUESTAS HABILITADAS'}
        </p>
        <p>Acción Propuesta Ollama ({llmConfig?.model_name}): {latestCycle?.llm?.proposal?.action}</p>
        <p>Motivo Breve: {latestCycle?.llm?.proposal?.justification}</p>
        <p>Estado de Riesgo: {latestCycle?.risk?.risk_status} — {latestCycle?.risk?.reason}</p>
      </div>

      <div className="strategy-comparison">
        <h3>Comparación de Estrategias (Capital $50,000 USDC, Comisión 0.0%)</h3>
        <table>
          <thead>
            <tr>
              <th>Estrategia</th>
              <th>Rendimiento Neto</th>
              <th>Max Drawdown</th>
              <th>Win Rate</th>
              <th>Operaciones</th>
              <th>Latencia</th>
              <th>Rechazadas</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((s) => (
              <tr key={s.strategy}>
                <td>{s.strategy}</td>
                <td>${s.net_return_usdc.toFixed(2)} ({s.net_return_pct}%)</td>
                <td>{s.max_drawdown_pct}%</td>
                <td>{s.win_rate_pct}%</td>
                <td>{s.operations_count}</td>
                <td>{s.mean_latency_ms} ms</td>
                <td>{s.rejected_actions}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="errors-grid">
        {errorSuite.map((e) => (
          <button key={e.scenario_code} onClick={() => triggerErrorScenario(e.scenario_code)}>
            Probar {e.scenario_code}
          </button>
        ))}
      </div>

      <div className="decisions-tabs">
        <button onClick={() => setDecisionTab('REPLAY')}>Replay ({replayDecisions.length})</button>
        <button onClick={() => setDecisionTab('LIVE')}>Live ({liveDecisions.length})</button>
      </div>
    </section>
  );
};
export default PolymarketAgentDashboard;

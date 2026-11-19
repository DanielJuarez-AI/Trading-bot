import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")
ORCHESTRATOR_STATE_PATH = os.path.join(CHECKPOINT_DIR, "laya_agents_state.json")


class MarketScoutAgent:
    """
    Agente 1: Explorador de Mercados y Régimen de Volatilidad.
    Evalúa la microestructura del CLOB de Polymarket y clasifica el régimen de volatilidad 5m de BTC.
    """

    name = "MarketScoutAgent"
    role = "Explorador CLOB & Régimen BTC 5m"

    def analyze(
        self,
        market_question: str,
        token_id: str,
        btc_price: float,
        parkinson_vol_series: np.ndarray,
        poly_real_series: np.ndarray,
        book_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_vol = float(parkinson_vol_series[-1])
        mean_vol = float(np.mean(parkinson_vol_series))
        p75_vol = float(np.percentile(parkinson_vol_series, 75))
        p90_vol = float(np.percentile(parkinson_vol_series, 90))

        if current_vol >= p90_vol:
            regime = "EXPLOSION_VOLATILIDAD"
        elif current_vol >= p75_vol:
            regime = "ALTA_VOLATILIDAD"
        elif current_vol >= mean_vol * 0.75:
            regime = "REGIMEN_NORMAL"
        else:
            regime = "COMPRESION_BAJA_VOL"

        spread = float(book_metrics.get("spread", 0.015))
        imbalance = float(book_metrics.get("imbalance", 0.0))
        current_poly = float(poly_real_series[-1])

        # Puntaje de calidad de liquidez (0 a 100)
        liquidity_score = round(max(10.0, min(99.0, 100.0 - spread * 450.0 + abs(imbalance) * 15.0)), 1)

        return {
            "agent": self.name,
            "role": self.role,
            "status": "ACTIVO",
            "market_question": market_question,
            "token_id": token_id[:16] + "..." if token_id else "N/A",
            "btc_price": round(btc_price, 2),
            "current_vol_pct": round(current_vol * 100.0, 4),
            "regime": regime,
            "poly_prob_pct": round(current_poly * 100.0, 2),
            "clob_spread_pct": round(spread * 100.0, 2),
            "clob_imbalance_pct": round(imbalance * 100.0, 1),
            "liquidity_score": liquidity_score,
        }


class AutoTrainerAgent:
    """
    Agente 2: Gobernador de Aprendizaje por Refuerzo y Calibración.
    Recibe el régimen desde MarketScoutAgent, ajusta hiperparámetros (épocas, lr, epsilon)
    y ejecuta la actualización Actor-Critic de Laya.
    """

    name = "AutoTrainerAgent"
    role = "Gobernador RL Actor-Critic & Brier"

    def tune_and_train(
        self,
        rl_agent,
        scout_report: Dict[str, Any],
        X_states: np.ndarray,
        y_true_high_vol: np.ndarray,
        parkinson_vol: np.ndarray,
        poly_real: np.ndarray,
        base_epochs: int = 12,
        feedback_bonus_epochs: int = 0,
    ) -> Dict[str, Any]:
        regime = scout_report["regime"]

        # Ajustar hiperparámetros dinámicamente según el régimen detectado por el Agente 1
        if regime == "EXPLOSION_VOLATILIDAD":
            rl_agent.lr = 0.022
            rl_agent.epsilon = max(0.05, rl_agent.epsilon)
            epochs = max(base_epochs, 24) + feedback_bonus_epochs
            mode_desc = "Adaptación Rápida (Alta Volatilidad)"
        elif regime == "ALTA_VOLATILIDAD":
            rl_agent.lr = 0.018
            epochs = max(base_epochs, 18) + feedback_bonus_epochs
            mode_desc = "Refuerzo Intensivo"
        elif regime == "COMPRESION_BAJA_VOL":
            rl_agent.lr = 0.011
            epochs = max(8, base_epochs) + feedback_bonus_epochs
            mode_desc = "Conservación de Pesos (Baja Vol)"
        else:
            rl_agent.lr = 0.015
            epochs = base_epochs + feedback_bonus_epochs
            mode_desc = "Calibración Estándar"

        spread = scout_report["clob_spread_pct"] / 100.0
        rl_out = rl_agent.train_realtime_step(
            X_states=X_states,
            y_true_high_vol=y_true_high_vol,
            parkinson_vol=parkinson_vol,
            poly_real=poly_real,
            clob_spread=min(0.05, spread),
            epochs_per_update=epochs,
        )

        probs = rl_out["probs"]
        latest_conf = float(probs[-1])
        opt_thresh = float(rl_out["optimal_threshold"])
        point1_conf_pct = float(
            rl_out.get(
                "point1_model_confidence_pct",
                round(0.55 * float(rl_out["calibration_index_pct"]) + 0.45 * (latest_conf * 100.0), 2),
            )
        )
        raw_bool = bool(latest_conf >= opt_thresh and point1_conf_pct > 85.0)

        return {
            "agent": self.name,
            "role": self.role,
            "status": "CALIBRADO",
            "training_mode": mode_desc,
            "epochs_executed": epochs,
            "learning_rate": round(rl_agent.lr, 4),
            "raw_boolean": raw_bool,
            "latest_confidence_pct": round(latest_conf * 100.0, 2),
            "point1_model_confidence_pct": round(point1_conf_pct, 2),
            "point1_passes_85": bool(point1_conf_pct > 85.0),
            "optimal_threshold": opt_thresh,
            "temperature": rl_out["temperature"],
            "calibration_index_pct": rl_out["calibration_index_pct"],
            "brier_after": rl_out["brier_after"],
            "win_rate_pct": rl_out["win_rate_pct"],
            "rl_full_output": rl_out,
        }


class RiskManagerAgent:
    """
    Agente 3: Gestor de Riesgo, Poder de Veto y Criterio de Kelly.
    Recibe la señal booleana del Agente 2 y la liquidez del Agente 1.
    Calcula el Edge Neto y decide si aprueba o veta la apuesta booleana.
    """

    name = "RiskManagerAgent"
    role = "Control de Riesgo, Veto & Criterio Kelly"

    def evaluate_risk(
        self,
        scout_report: Dict[str, Any],
        trainer_report: Dict[str, Any],
        laya_model_prob: float,
        poly_real_prob: float,
        bankroll_usd: float,
        remaining_window_sec: int = 180,
    ) -> Dict[str, Any]:
        raw_bool = trainer_report["raw_boolean"]
        conf = trainer_report["latest_confidence_pct"] / 100.0
        calib = trainer_report["calibration_index_pct"] / 100.0
        point1_conf_pct = float(trainer_report.get("point1_model_confidence_pct", conf * 100.0))
        opt_thresh = trainer_report["optimal_threshold"]

        raw_edge = laya_model_prob - poly_real_prob
        effective_spread = min(0.035, (scout_report["clob_spread_pct"] / 100.0) * 0.25)
        net_edge = raw_edge - effective_spread
        liquidity_score = float(scout_report.get("liquidity_score", 80.0))

        # Punto 2: Confianza determinista de riesgo y Kelly fraccional (0-100%)
        if net_edge <= 0.001 or calib < 0.72:
            point2_risk_conf_pct = round(
                float(np.clip(35.0 + (liquidity_score / 100.0) * 20.0 + max(-0.02, net_edge) * 200.0, 0.0, 62.0)),
                2,
            )
        else:
            edge_component = min(1.0, max(0.0, net_edge / 0.015)) * 30.0
            liq_component = min(1.0, max(0.0, liquidity_score / 100.0)) * 35.0
            calib_component = min(1.0, max(0.0, calib)) * 35.0
            point2_risk_conf_pct = round(float(np.clip(edge_component + liq_component + calib_component, 0.0, 99.5)), 2)

        last_minute_locked = bool(int(remaining_window_sec) < 60)
        dual_85_passed = bool(point1_conf_pct > 85.0 and point2_risk_conf_pct > 85.0)

        veto_applied = False
        veto_reason = "Señal validada sin objeciones"

        if last_minute_locked:
            veto_applied = True
            veto_reason = "BLOQUEO ÚLTIMO MINUTO (<60s): Apuestas deshabilitadas hasta el siguiente periodo 5m"
        elif net_edge <= 0.001:
            veto_applied = True
            veto_reason = f"VETO: Edge bruto (+{raw_edge*100:.2f}%) no supera costo de spread"
        elif calib < 0.72:
            veto_applied = True
            veto_reason = f"VETO: Fiabilidad Brier ({calib*100:.1f}%) por debajo del mínimo (72%)"
        elif not dual_85_passed:
            veto_reason = (
                f"EN ESPERA (>85% requerido): Punto 1 Modelo={point1_conf_pct:.1f}% | "
                f"Punto 2 Riesgo={point2_risk_conf_pct:.1f}%"
            )
        else:
            veto_reason = (
                f"APROBADO (>85% DUAL): Punto 1={point1_conf_pct:.1f}% & "
                f"Punto 2={point2_risk_conf_pct:.1f}% con Edge neto positivo"
            )

        approved_boolean = bool(
            not last_minute_locked
            and not veto_applied
            and dual_85_passed
            and raw_bool
        )

        # Cálculo de Criterio de Kelly Fraccional (0.25x Kelly por seguridad en velas de 5m)
        if approved_boolean:
            b_odds = max(0.25, (1.0 - poly_real_prob) / max(0.05, poly_real_prob))
            p_win = min(0.92, max(0.51, conf))
            q_lose = 1.0 - p_win
            kelly_raw = max(0.0, (p_win * b_odds - q_lose) / b_odds)
            kelly_fraction = min(0.08, kelly_raw * 0.25)  # Máximo 8% de la banca por vela de 5m
        else:
            kelly_fraction = 0.0

        stake_usd = round(bankroll_usd * kelly_fraction, 2)
        risk_level = (
            "BLOQUEO_ULTIMO_MINUTO"
            if last_minute_locked
            else ("ALTO" if kelly_fraction > 0.05 else ("MODERADO" if kelly_fraction > 0.01 else "NEUTRAL (0%)"))
        )

        return {
            "agent": self.name,
            "role": self.role,
            "status": (
                "BLOQUEADO (<60s)"
                if last_minute_locked
                else ("VETO ACTIVO" if veto_applied else ("ORDEN APROBADA" if approved_boolean else "PROTECCIÓN CAPITAL"))
            ),
            "raw_boolean": raw_bool,
            "approved_boolean": approved_boolean,
            "veto_applied": veto_applied,
            "veto_reason": veto_reason,
            "point1_model_confidence_pct": round(point1_conf_pct, 2),
            "point2_risk_confidence_pct": point2_risk_conf_pct,
            "dual_85_passed": dual_85_passed,
            "last_minute_locked": last_minute_locked,
            "remaining_window_sec": int(remaining_window_sec),
            "raw_edge_pct": round(raw_edge * 100.0, 2),
            "net_edge_pct": round(net_edge * 100.0, 2),
            "kelly_fraction_pct": round(kelly_fraction * 100.0, 2),
            "stake_usd": stake_usd,
            "risk_level": risk_level,
            "optimal_threshold_used": opt_thresh,
        }


class ExecutionAuditorAgent:
    """
    Agente 4: Ejecutor CLOB y Auditor de Rendimiento.
    Ejecuta/simula las órdenes aprobadas por RiskManagerAgent, audita el PnL acumulado
    y envía retroalimentación de recompensa al Agente 2 (AutoTrainerAgent).
    """

    name = "ExecutionAuditorAgent"
    role = "Ejecución CLOB, Auditoría PnL & Feedback"

    def __init__(self):
        self.bankroll_usd = 1000.0
        self.cumulative_pnl_usd = 0.0
        self.executed_trades = 0
        self.vetoed_trades = 0
        self.winning_trades = 0
        self.last_processed_ts = 0
        self.load_state()

    def execute_and_audit(
        self,
        candle_timestamp: int,
        risk_report: Dict[str, Any],
        latest_rl_reward: float,
    ) -> Dict[str, Any]:
        approved = risk_report["approved_boolean"]
        vetoed = risk_report["veto_applied"]
        stake = risk_report["stake_usd"]

        action_taken = "HOLD (Sin Entrada)"
        last_trade_pnl = 0.0

        # Contabilizar una vez por vela o ciclo de actualización significativo
        if candle_timestamp != self.last_processed_ts:
            self.last_processed_ts = candle_timestamp
            if vetoed:
                self.vetoed_trades += 1
                action_taken = "BLOQUEADA POR RIESGO"
            elif approved and stake > 0:
                self.executed_trades += 1
                # Rendimiento proporcional a la recompensa verificada en la ventana
                roi = np.clip(latest_rl_reward * 0.085, -0.15, 0.22)
                last_trade_pnl = round(float(stake * roi), 2)
                self.bankroll_usd = round(self.bankroll_usd + last_trade_pnl, 2)
                self.cumulative_pnl_usd = round(self.bankroll_usd - 1000.0, 2)
                if last_trade_pnl >= 0:
                    self.winning_trades += 1
                action_taken = f"BET TRUE (${stake:.2f})"
        else:
            if vetoed:
                action_taken = "BLOQUEADA POR RIESGO"
            elif approved and stake > 0:
                action_taken = f"ORDEN ACTIVA (${stake:.2f})"

        feedback_bonus_epochs = 6 if latest_rl_reward < 0 else 0
        feedback_msg = (
            "Reforzar pesos (+6 épocas extra)"
            if feedback_bonus_epochs > 0
            else "Política estable (Mantener cadencia)"
        )

        self.save_state()

        return {
            "agent": self.name,
            "role": self.role,
            "status": action_taken,
            "bankroll_usd": self.bankroll_usd,
            "cumulative_pnl_usd": self.cumulative_pnl_usd,
            "executed_trades": self.executed_trades,
            "vetoed_trades": self.vetoed_trades,
            "winning_trades": self.winning_trades,
            "last_trade_pnl_usd": last_trade_pnl,
            "feedback_bonus_epochs": feedback_bonus_epochs,
            "feedback_signal": feedback_msg,
        }

    def save_state(self) -> None:
        try:
            os.makedirs(CHECKPOINT_DIR, exist_ok=True)
            with open(ORCHESTRATOR_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "bankroll_usd": self.bankroll_usd,
                        "cumulative_pnl_usd": self.cumulative_pnl_usd,
                        "executed_trades": self.executed_trades,
                        "vetoed_trades": self.vetoed_trades,
                        "winning_trades": self.winning_trades,
                        "last_processed_ts": self.last_processed_ts,
                    },
                    f,
                    indent=2,
                )
        except Exception:
            pass

    def load_state(self) -> None:
        if os.path.exists(ORCHESTRATOR_STATE_PATH):
            try:
                with open(ORCHESTRATOR_STATE_PATH, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.bankroll_usd = float(d.get("bankroll_usd", 1000.0))
                self.cumulative_pnl_usd = float(d.get("cumulative_pnl_usd", 0.0))
                self.executed_trades = int(d.get("executed_trades", 0))
                self.vetoed_trades = int(d.get("vetoed_trades", 0))
                self.winning_trades = int(d.get("winning_trades", 0))
                self.last_processed_ts = int(d.get("last_processed_ts", 0))
            except Exception:
                pass


class LayaMultiAgentOrchestrator:
    """
    Orquestador Central que coordina los 4 agentes inteligentes y construye
    el Bus de Mensajes en Tiempo Real para visualizar cómo comparten información.
    """

    def __init__(self, rl_agent):
        self.rl_agent = rl_agent
        self.scout = MarketScoutAgent()
        self.trainer = AutoTrainerAgent()
        self.risk = RiskManagerAgent()
        self.executor = ExecutionAuditorAgent()
        self.last_feedback_epochs = 0

    def run_cycle(
        self,
        market_question: str,
        token_id: str,
        open_times: np.ndarray,
        closes: np.ndarray,
        parkinson_vol: np.ndarray,
        poly_real: np.ndarray,
        X_states: np.ndarray,
        y_true_high_vol: np.ndarray,
        book_metrics: Dict[str, Any],
        base_epochs: int = 12,
        remaining_window_sec: int = 180,
    ) -> Dict[str, Any]:
        now_str = datetime.now().strftime("%H:%M:%S")

        # 1. Agente Explorador analiza mercado y régimen
        scout_rep = self.scout.analyze(
            market_question=market_question,
            token_id=token_id,
            btc_price=float(closes[-1]),
            parkinson_vol_series=parkinson_vol,
            poly_real_series=poly_real,
            book_metrics=book_metrics,
        )

        # 2. Agente Entrenador RL ajusta hiperparámetros y entrena a Laya
        trainer_rep = self.trainer.tune_and_train(
            rl_agent=self.rl_agent,
            scout_report=scout_rep,
            X_states=X_states,
            y_true_high_vol=y_true_high_vol,
            parkinson_vol=parkinson_vol,
            poly_real=poly_real,
            base_epochs=base_epochs,
            feedback_bonus_epochs=self.last_feedback_epochs,
        )
        rl_out = trainer_rep["rl_full_output"]
        laya_conf = rl_out["probs"]

        # Curva estimada por Laya
        vol_spread_amp = max(0.03, np.std(poly_real) * 1.35)
        laya_edge_series = (laya_conf - 0.50) * (vol_spread_amp * 2.1)
        laya_model_curve = np.clip(poly_real + laya_edge_series, 0.01, 0.99)

        # 3. Agente de Riesgo evalúa el booleano, aplica Veto o calcula Kelly
        risk_rep = self.risk.evaluate_risk(
            scout_report=scout_rep,
            trainer_report=trainer_rep,
            laya_model_prob=float(laya_model_curve[-1]),
            poly_real_prob=float(poly_real[-1]),
            bankroll_usd=self.executor.bankroll_usd,
            remaining_window_sec=remaining_window_sec,
        )

        # 4. Agente Ejecutor y Auditor registra la orden y retroalimenta al Entrenador
        exec_rep = self.executor.execute_and_audit(
            candle_timestamp=int(open_times[-1]),
            risk_report=risk_rep,
            latest_rl_reward=float(rl_out["rewards"][-1]),
        )
        self.last_feedback_epochs = exec_rep["feedback_bonus_epochs"]

        # Bus de Mensajes Inter-Agente (Paquetes compartidos en este ciclo)
        message_bus: List[Dict[str, Any]] = [
            {
                "id": "MSG-1",
                "time": now_str,
                "from": "MarketScoutAgent",
                "to": "AutoTrainerAgent",
                "channel": "TELEMETRIA_MERCADO_5M",
                "summary": f"Régimen: {scout_rep['regime']} | Vol 5m: {scout_rep['current_vol_pct']}% | Liquidez: {scout_rep['liquidity_score']}/100",
                "payload": {
                    "regime": scout_rep["regime"],
                    "btc_vol_5m_pct": scout_rep["current_vol_pct"],
                    "poly_prob_pct": scout_rep["poly_prob_pct"],
                    "clob_spread_pct": scout_rep["clob_spread_pct"],
                },
            },
            {
                "id": "MSG-2",
                "time": now_str,
                "from": "AutoTrainerAgent",
                "to": "RiskManagerAgent",
                "channel": "INFERENCIA_BOOLEANA_RL",
                "summary": f"Booleano Bruto: {trainer_rep['raw_boolean']} | Punto 1 Modelo: {trainer_rep['point1_model_confidence_pct']}% (>85%={trainer_rep['point1_passes_85']}) | Umbral={trainer_rep['optimal_threshold']} | Calib: {trainer_rep['calibration_index_pct']}%",
                "payload": {
                    "raw_boolean": trainer_rep["raw_boolean"],
                    "confidence_pct": trainer_rep["latest_confidence_pct"],
                    "point1_model_confidence_pct": trainer_rep["point1_model_confidence_pct"],
                    "point1_passes_85": trainer_rep["point1_passes_85"],
                    "optimal_threshold": trainer_rep["optimal_threshold"],
                    "temperature": trainer_rep["temperature"],
                    "epochs_run": trainer_rep["epochs_executed"],
                },
            },
            {
                "id": "MSG-3",
                "time": now_str,
                "from": "RiskManagerAgent",
                "to": "ExecutionAuditorAgent",
                "channel": "VALIDACION_KELLY_Y_VETO",
                "summary": f"Decisión Final: {risk_rep['approved_boolean']} | Punto 2 Riesgo: {risk_rep['point2_risk_confidence_pct']}% | Dual>85%: {risk_rep['dual_85_passed']} | {risk_rep['veto_reason']}",
                "payload": {
                    "approved_boolean": risk_rep["approved_boolean"],
                    "veto_applied": risk_rep["veto_applied"],
                    "point1_model_confidence_pct": risk_rep["point1_model_confidence_pct"],
                    "point2_risk_confidence_pct": risk_rep["point2_risk_confidence_pct"],
                    "dual_85_passed": risk_rep["dual_85_passed"],
                    "last_minute_locked": risk_rep["last_minute_locked"],
                    "remaining_window_sec": risk_rep["remaining_window_sec"],
                    "net_edge_pct": risk_rep["net_edge_pct"],
                    "kelly_stake_usd": risk_rep["stake_usd"],
                },
            },
            {
                "id": "MSG-4",
                "time": now_str,
                "from": "ExecutionAuditorAgent",
                "to": "AutoTrainerAgent",
                "channel": "RETROALIMENTACION_RECOMPENSA",
                "summary": f"Estado: {exec_rep['status']} | Banca: ${exec_rep['bankroll_usd']} (PnL: ${exec_rep['cumulative_pnl_usd']}) | {exec_rep['feedback_signal']}",
                "payload": {
                    "bankroll_usd": exec_rep["bankroll_usd"],
                    "cumulative_pnl_usd": exec_rep["cumulative_pnl_usd"],
                    "reward_rt": round(float(rl_out["rewards"][-1]), 4),
                    "bonus_epochs_next": exec_rep["feedback_bonus_epochs"],
                },
            },
        ]

        # Limpiar rl_full_output del reporte serializable del agente 2
        trainer_clean = {k: v for k, v in trainer_rep.items() if k != "rl_full_output"}

        return {
            "rl_out": rl_out,
            "laya_model_curve": laya_model_curve,
            "laya_edge_series": laya_edge_series,
            "agents": {
                "scout": scout_rep,
                "trainer": trainer_clean,
                "risk": risk_rep,
                "executor": exec_rep,
            },
            "message_bus": message_bus,
        }

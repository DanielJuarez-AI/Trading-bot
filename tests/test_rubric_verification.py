import json
import os
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from polymarket_final_agent import PolymarketFinalAgentEngine
from server import fetch_btc_5m_klines


class TestPolymarketFinalProjectRubric(unittest.TestCase):
    """
    Pruebas automatizadas de los 8 criterios de la Rúbrica Independiente de 100 Puntos
    (Secciones 14, 15 y 16) enfocada en Polymarket.
    """

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_polymarket_agent.db")
        cls.engine = PolymarketFinalAgentEngine(db_path=cls.test_db_path)
        cls.sample_klines = fetch_btc_5m_klines(limit=96)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_01_integration_and_versioned_model_15pts(self):
        """Criterio 1 (15 pts): Modelo y escalador versionados, Ollama local y UI React+TS."""
        self.assertTrue(os.path.exists(os.path.join(BASE_DIR, "checkpoints", "laya_rl_weights.npz")))
        self.assertTrue(os.path.exists(os.path.join(BASE_DIR, "checkpoints", "laya_scaler_v1.json")))
        self.assertTrue(os.path.exists(os.path.join(BASE_DIR, "checkpoints", "model_contract_v1.json")))
        self.assertTrue(os.path.exists(os.path.join(BASE_DIR, "checkpoints", "training_evidence_t4.json")))
        self.assertTrue(
            os.path.exists(os.path.join(BASE_DIR, "frontend", "src", "react", "PolymarketAgentDashboard.tsx"))
        )

        # Verificar inferencia local en Ollama sin nube
        obs = {
            "symbol": "POLY-BTC-5M",
            "candle_date": "2026-11-17T20:20:00Z",
            "model_forecast_prob": 0.61,
            "poly_clob_prob": 0.52,
            "optimal_threshold": 0.54,
            "indicators": {"parkinson_vol_5m": 0.0018, "taker_buy_ratio_5m": 0.55},
        }
        res = self.engine.gateway.query_local_ollama(structured_observation=obs)
        self.assertTrue(res["ok"])
        self.assertFalse(res["cloud_inference"])
        self.assertGreater(res["latency_ms"], 0.0)
        self.assertIn(res["proposal"]["action"], {"BUY", "HOLD", "SELL"})

    def test_02_private_api_and_secrets_10pts(self):
        """Criterio 2 (10 pts): Autenticación del Gateway y rechazo de claves ausentes o inválidas; sin secretos en UI."""
        # Clave ausente
        ok_missing, _ = self.engine.gateway.verify_api_key(None, "UnitTestGateway")
        self.assertFalse(ok_missing)

        # Clave incorrecta
        ok_bad, _ = self.engine.gateway.verify_api_key("wrong-key-123", "UnitTestGateway")
        self.assertFalse(ok_bad)

        # Clave correcta del servidor
        valid_key = self.engine.gateway._get_gateway_secret()
        ok_good, _ = self.engine.gateway.verify_api_key(valid_key, "UnitTestGateway")
        self.assertTrue(ok_good)

        # Verificar que .env.example existe y solo contiene placeholders (sin secretos reales)
        env_example = os.path.join(BASE_DIR, ".env.example")
        self.assertTrue(os.path.exists(env_example))
        with open(env_example, "r", encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("REEMPLAZAR_CON_SECRETO", txt)
        if valid_key:
            self.assertNotIn(valid_key, txt)

    def test_03_polymarket_data_and_paper_simulator_15pts(self):
        """Criterio 3 (15 pts): Velas cerradas válidas, simulador con $50,000 USDC y 0.0% costo, bloqueo de órdenes reales."""
        state = self.engine.db.reset_portfolio(clear_replay=True)
        self.assertEqual(state["cash_usdc"], 50000.0)
        self.assertEqual(self.engine.risk_config["fee_rate_pct"], 0.0)
        self.assertFalse(self.engine.risk_config["allow_leverage"])
        self.assertFalse(self.engine.risk_config["allow_short_selling"])

        # Verificar bloqueo determinista de órdenes reales
        real_block = self.engine.attempt_real_polymarket_order_block()
        self.assertFalse(real_block["ok"])
        self.assertTrue(real_block["blocked"])
        self.assertEqual(real_block["error_code"], "REAL_ORDER_BLOCKED")

    def test_04_mandatory_7step_cycle_and_validation_15pts(self):
        """Criterio 4 (15 pts): Ciclo obligatorio de 7 pasos y validación estricta de JSON."""
        self.engine.db.reset_portfolio(clear_replay=True)
        res = self.engine.run_mandatory_7step_cycle(
            raw_klines=self.sample_klines,
            poly_clob_prob=0.51,
            mode="LIVE",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["steps_verified"]), 7)
        self.assertIn(res["llm"]["proposal"]["action"], {"BUY", "HOLD", "SELL"})
        self.assertEqual(res["llm"]["proposal"]["symbol"], "POLY-BTC-5M")

    def test_05_deterministic_risk_and_human_controls_10pts(self):
        """Criterio 5 (10 pts): Límites deterministas e Iniciar, Pausar y Detener sin asumir liquidación."""
        # Iniciar
        r_start = self.engine.set_human_control("START")
        self.assertEqual(r_start["status"], "RUNNING")

        # Pausar
        r_pause = self.engine.set_human_control("PAUSE")
        self.assertEqual(r_pause["status"], "PAUSED")

        # Detener conservando posición (stop_liquidates_position = False)
        r_stop = self.engine.set_human_control("STOP", liquidate_on_stop=False)
        self.assertEqual(r_stop["status"], "STOPPED")

        # Verificar que estando STOPPED se bloquean nuevas compras
        risk_blocked = self.engine.evaluate_deterministic_risk(
            llm_action="BUY",
            symbol="POLY-BTC-5M",
            candle_timestamp=1999999999,
            mode="LIVE",
            poly_clob_prob=0.52,
            data_age_sec=5.0,
        )
        self.assertFalse(risk_blocked["approved"])
        self.engine.set_human_control("START")

    def test_06_nine_errors_persistence_and_20_cycles_15pts(self):
        """Criterio 6 (15 pts): 9 escenarios de error, persistencia sin duplicados y >=20 ciclos Replay."""
        err_suite = self.engine.demonstrate_all_9_errors(self.sample_klines)
        self.assertEqual(err_suite["total_scenarios"], 9)
        self.assertEqual(err_suite["passed_scenarios"], 9)
        self.assertTrue(err_suite["all_9_verified"])

        replay_res = self.engine.run_20_replay_cycles(self.sample_klines, num_cycles=22)
        self.assertGreaterEqual(replay_res["total_replay_cycles_verified"], 20)
        self.assertTrue(replay_res["separated_from_live"])

    def test_07_three_strategies_evaluation_10pts(self):
        """Criterio 7 (10 pts): Comparación sin LLM, con LLM y Comprar y Mantener con mismo periodo y costos."""
        comp = self.engine.evaluate_three_strategies(self.sample_klines)
        strats = comp["strategies"]
        for key in ("model_without_llm", "agent_with_llm", "buy_and_hold"):
            self.assertIn(key, strats)
            s = strats[key]
            self.assertEqual(s["initial_capital_usdc"], 50000.0)
            self.assertIn("net_return_usdc", s)
            self.assertIn("max_drawdown_pct", s)
            self.assertIn("win_rate_pct", s)
            self.assertIn("operations_count", s)
            self.assertIn("mean_latency_ms", s)
            self.assertIn("rejected_actions", s)

    def test_08_dual_85_confidence_and_last_minute_lockout(self):
        """Punto 1 + Punto 2 > 85% para operar y bloqueo en el último minuto (<60s) con reinicio al siguiente periodo."""
        self.engine.db.reset_portfolio(clear_replay=True)
        self.engine.set_human_control("START")

        # 1. Cuando Punto 1 > 85% y Punto 2 > 85% y remaining_window_sec >= 60 (180s), aprueba la compra
        res_ok = self.engine.evaluate_deterministic_risk(
            llm_action="BUY",
            symbol="POLY-BTC-5M",
            candle_timestamp=1900000100,
            mode="TEST_DUAL_85",
            poly_clob_prob=0.52,
            data_age_sec=5.0,
            remaining_window_sec=180,
            point1_conf_pct=87.5,
            point2_conf_pct=88.2,
        )
        self.assertTrue(res_ok["approved"])
        self.assertEqual(res_ok["risk_status"], "APPROVED_BUY")
        self.assertEqual(res_ok["final_action"], "BUY")
        self.assertFalse(res_ok["last_minute_locked"])
        self.assertTrue(res_ok["dual_85_passed"])

        # 2. Cuando Punto 1 <= 85% o Punto 2 <= 85%, NO se ejecuta operación (HOLD)
        res_low_p1 = self.engine.evaluate_deterministic_risk(
            llm_action="BUY",
            symbol="POLY-BTC-5M",
            candle_timestamp=1900000200,
            mode="TEST_DUAL_85",
            poly_clob_prob=0.52,
            data_age_sec=5.0,
            remaining_window_sec=180,
            point1_conf_pct=84.9,
            point2_conf_pct=91.0,
        )
        self.assertFalse(res_low_p1["approved"])
        self.assertEqual(res_low_p1["risk_status"], "WAIT_DUAL_CONFIDENCE_85")
        self.assertEqual(res_low_p1["final_action"], "HOLD")

        res_low_p2 = self.engine.evaluate_deterministic_risk(
            llm_action="BUY",
            symbol="POLY-BTC-5M",
            candle_timestamp=1900000300,
            mode="TEST_DUAL_85",
            poly_clob_prob=0.52,
            data_age_sec=5.0,
            remaining_window_sec=180,
            point1_conf_pct=90.5,
            point2_conf_pct=85.0,
        )
        self.assertFalse(res_low_p2["approved"])
        self.assertEqual(res_low_p2["risk_status"], "WAIT_DUAL_CONFIDENCE_85")
        self.assertEqual(res_low_p2["final_action"], "HOLD")

        # 3. En el último minuto (< 60s, ej. 45s), las apuestas quedan deshabilitadas aunque ambas superen 85%
        res_locked = self.engine.evaluate_deterministic_risk(
            llm_action="BUY",
            symbol="POLY-BTC-5M",
            candle_timestamp=1900000400,
            mode="TEST_DUAL_85",
            poly_clob_prob=0.52,
            data_age_sec=5.0,
            remaining_window_sec=45,
            point1_conf_pct=93.0,
            point2_conf_pct=94.0,
        )
        self.assertFalse(res_locked["approved"])
        self.assertEqual(res_locked["risk_status"], "LOCKED_LAST_MINUTE_5M")
        self.assertEqual(res_locked["final_action"], "HOLD")
        self.assertTrue(res_locked["last_minute_locked"])

        # Verificar también que get_window_timing detecta el último minuto y la reapertura
        timing_locked = self.engine.get_window_timing(now_utc_sec=1900000455.0)  # +255s en ventana -> quedan 45s
        self.assertTrue(timing_locked["last_minute_locked"])
        self.assertFalse(timing_locked["betting_enabled"])

        # 4. Al iniciar el siguiente periodo (remaining_window_sec = 295 >= 60), se reactivan las apuestas
        timing_next = self.engine.get_window_timing(now_utc_sec=1900000505.0)  # +5s en siguiente ventana -> quedan 295s
        self.assertFalse(timing_next["last_minute_locked"])
        self.assertTrue(timing_next["betting_enabled"])

        res_reopened = self.engine.evaluate_deterministic_risk(
            llm_action="BUY",
            symbol="POLY-BTC-5M",
            candle_timestamp=1900000500,
            mode="TEST_DUAL_85",
            poly_clob_prob=0.52,
            data_age_sec=5.0,
            remaining_window_sec=timing_next["remaining_sec"],
            point1_conf_pct=90.0,
            point2_conf_pct=91.0,
        )
        self.assertTrue(res_reopened["approved"])
        self.assertEqual(res_reopened["risk_status"], "APPROVED_BUY")
        self.assertFalse(res_reopened["last_minute_locked"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

import json
import os
import time
from typing import Dict, Any, List, Tuple
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")
RL_WEIGHTS_PATH = os.path.join(CHECKPOINT_DIR, "laya_rl_weights.npz")
RL_METRICS_PATH = os.path.join(CHECKPOINT_DIR, "laya_rl_history.json")


class LayaRLAgent:
    """
    Agente de Aprendizaje por Refuerzo en Tiempo Real (Actor-Critic + Calibración Brier)
    para el modelo Laya sobre la volatilidad a 5 minutos de Bitcoin y Polymarket CLOB.

    - Estado (s_t): Vector de 8 dimensiones (Parkinson 5m, Garman-Klass 5m, Vol Realizada,
      Retorno Log 5m, Z-Score Volumen, Taker Buy Ratio, Precio Real Polymarket, Momentum Polymarket).
    - Acción (a_t): Booleano {False (0), True (1)}.
    - Recompensa (R_t): Recompensa asimétrica de mercado ajustada por el spread del CLOB de Polymarket
      menos penalización cuadrática de Brier (p_t - y_{t+1})^2 para calibrar la confianza.
    """

    def __init__(self, state_dim: int = 8, hidden_dim: int = 32, gamma: float = 0.92, lr: float = 0.015):
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.gamma = gamma
        self.lr = lr

        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        rng = np.random.default_rng(101)

        # Parámetros del Actor (Política Booleana y Confianza de Laya)
        self.W1_actor = rng.normal(0, 0.25, (state_dim, hidden_dim))
        self.b1_actor = np.zeros(hidden_dim)
        self.W2_actor = rng.normal(0, 0.25, (hidden_dim, 1))
        self.b2_actor = np.zeros(1)

        # Parámetros del Crítico V(s) para estimar la Ventaja (Advantage A_t)
        self.W1_critic = rng.normal(0, 0.25, (state_dim, hidden_dim))
        self.b1_critic = np.zeros(hidden_dim)
        self.W2_critic = rng.normal(0, 0.25, (hidden_dim, 1))
        self.b2_critic = np.zeros(1)

        # Parámetros adaptativos de calibración de confianza
        self.temperature = 1.0  # Escala de temperatura de Platt/Sigmoid
        self.optimal_threshold = 0.55  # Umbral booleano ajustado por RL
        self.epsilon = 0.12  # Tasa de exploración inicial
        self.total_rl_steps = 0
        self.episodes_trained = 0
        self.reward_history: List[float] = []
        self.confidence_calibration_history: List[float] = []
        self.param_delta_norm = 0.0

        self.load_checkpoint()

    @staticmethod
    def _gelu(x: np.ndarray) -> np.ndarray:
        return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * (x ** 3))))

    @staticmethod
    def _gelu_deriv(x: np.ndarray) -> np.ndarray:
        # Aproximación rápida de la derivada de GELU
        s = 1.0 / (1.0 + np.exp(-1.702 * np.clip(x, -15, 15)))
        return s + x * 1.702 * s * (1.0 - s)

    @staticmethod
    def _sigmoid(x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -18.0, 18.0)))

    def forward_actor(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Devuelve (probabilidades_calibradas, pre_activacion_oculta, activacion_oculta).
        """
        z1 = X @ self.W1_actor + self.b1_actor
        a1 = self._gelu(z1)
        logits = (a1 @ self.W2_actor + self.b2_actor) / max(0.25, self.temperature)
        probs = self._sigmoid(logits)
        return probs, z1, a1

    def forward_critic(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Devuelve el valor estimado del estado V(s).
        """
        z1 = X @ self.W1_critic + self.b1_critic
        a1 = self._gelu(z1)
        v = a1 @ self.W2_critic + self.b2_critic
        return v, z1, a1

    def compute_market_rewards(
        self,
        actions: np.ndarray,
        probs: np.ndarray,
        y_true_high_vol: np.ndarray,
        parkinson_vol: np.ndarray,
        poly_delta: np.ndarray,
        clob_spread: float = 0.015,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calcula la recompensa de refuerzo en tiempo real para cada vela de 5 minutos:
        - Premia aciertos booleanos en explosiones de volatilidad y movimientos favorables en Polymarket.
        - Penaliza falsos positivos descontando el spread real del CLOB.
        - Incluye término de calibración de Brier para que la confianza refleje la probabilidad real.
        """
        n = len(actions)
        rewards = np.zeros(n, dtype=np.float64)
        vol_median = np.median(parkinson_vol) + 1e-8

        for t in range(n):
            act = int(actions[t])
            target = int(y_true_high_vol[t])
            vol_mag = min(2.0, float(parkinson_vol[t] / vol_median))
            p_move_bonus = float(np.clip(abs(poly_delta[t]) * 12.0, 0.0, 0.8))

            if act == 1 and target == 1:
                # Verdadero Positivo: Laya apostó True y hubo explosión real de volatilidad 5m
                r_raw = +1.15 + 0.35 * vol_mag + p_move_bonus - clob_spread
            elif act == 1 and target == 0:
                # Falso Positivo: Laya apostó True pero el mercado estuvo plano (penalización fuerte)
                r_raw = -1.25 - clob_spread
            elif act == 0 and target == 0:
                # Verdadero Negativo: Laya decidió esperar (False) y evitó ruido sin volatilidad
                r_raw = +0.35
            else:
                # Falso Negativo: Laya decidió esperar pero hubo movimiento fuerte
                r_raw = -0.45

            # Penalización de calibración Brier: fuerza a que `probs[t]` sea una confianza honesta
            brier_error = (float(probs[t]) - float(target)) ** 2
            rewards[t] = r_raw - 0.65 * brier_error

        # Calcular retornos descontados G_t hacia atrás
        returns = np.zeros(n, dtype=np.float64)
        running_g = 0.0
        for t in reversed(range(n)):
            running_g = rewards[t] + self.gamma * running_g
            returns[t] = running_g

        return rewards, returns

    def train_realtime_step(
        self,
        X_states: np.ndarray,
        y_true_high_vol: np.ndarray,
        parkinson_vol: np.ndarray,
        poly_real: np.ndarray,
        clob_spread: float = 0.015,
        epochs_per_update: int = 12,
    ) -> Dict[str, Any]:
        """
        Ejecuta un ciclo de entrenamiento por refuerzo Actor-Critic en tiempo real
        con los datos actuales de 5m de Polymarket y Bitcoin, ajustando los pesos
        y la temperatura de confianza de Laya.
        """
        n = len(X_states)
        poly_delta = np.zeros(n, dtype=np.float64)
        poly_delta[1:] = poly_real[1:] - poly_real[:-1]

        # Guardar copia de pesos iniciales para medir la magnitud del ajuste ||Δθ||
        w1_prev = self.W1_actor.copy()
        w2_prev = self.W2_actor.copy()

        # Evaluar calibración antes del refuerzo
        probs_before, _, _ = self.forward_actor(X_states)
        brier_before = float(np.mean((probs_before.flatten() - y_true_high_vol) ** 2))

        last_rewards = np.zeros(n)
        last_advantages = np.zeros(n)

        for _ in range(epochs_per_update):
            probs, z1_a, a1_a = self.forward_actor(X_states)
            p_flat = probs.flatten()

            # Selección de acción booleana con política estocástica + umbral
            rng = np.random.default_rng(int(time.time() * 1000) % 100000)
            explore_mask = rng.random(n) < self.epsilon
            random_actions = (rng.random(n) >= 0.5).astype(np.float64)
            greedy_actions = (p_flat >= self.optimal_threshold).astype(np.float64)
            actions = np.where(explore_mask, random_actions, greedy_actions)

            # Obtener recompensas del entorno en tiempo real
            rewards, returns = self.compute_market_rewards(
                actions=actions,
                probs=p_flat,
                y_true_high_vol=y_true_high_vol,
                parkinson_vol=parkinson_vol,
                poly_delta=poly_delta,
                clob_spread=clob_spread,
            )
            last_rewards = rewards

            # Evaluar Crítico V(s) y Ventaja (Advantage A_t = R_t + gamma*V(s_{t+1}) - V(s_t))
            values, z1_c, a1_c = self.forward_critic(X_states)
            v_flat = values.flatten()
            v_next = np.roll(v_flat, -1)
            v_next[-1] = 0.0
            td_target = rewards + self.gamma * v_next
            advantages = td_target - v_flat

            # Normalizar ventajas para estabilidad del gradiente de política
            adv_norm = (advantages - np.mean(advantages)) / (np.std(advantages) + 1e-8)
            last_advantages = advantages

            # --- 1. Actualización del Crítico (MSE sobre TD Target) ---
            dv = ((v_flat - td_target) / n).reshape(-1, 1)
            dW2_c = a1_c.T @ dv + 1e-4 * self.W2_critic
            db2_c = np.sum(dv, axis=0)
            da1_c = dv @ self.W2_critic.T
            dz1_c = da1_c * self._gelu_deriv(z1_c)
            dW1_c = X_states.T @ dz1_c + 1e-4 * self.W1_critic
            db1_c = np.sum(dz1_c, axis=0)

            self.W1_critic -= self.lr * dW1_c
            self.b1_critic -= self.lr * db1_c
            self.W2_critic -= self.lr * dW2_c
            self.b2_critic -= self.lr * db2_c

            # --- 2. Actualización del Actor (Policy Gradient + Calibración Directa) ---
            # Gradiente de log-probabilidad ponderado por ventaja + término de calibración supervisada suave
            pg_signal = (actions - p_flat) * adv_norm
            calib_signal = (y_true_high_vol - p_flat) * 0.55
            dlogits = (-(pg_signal + calib_signal) / n).reshape(-1, 1) / max(0.25, self.temperature)

            dW2_a = a1_a.T @ dlogits + 1e-4 * self.W2_actor
            db2_a = np.sum(dlogits, axis=0)
            da1_a = dlogits @ self.W2_actor.T
            dz1_a = da1_a * self._gelu_deriv(z1_a)
            dW1_a = X_states.T @ dz1_a + 1e-4 * self.W1_actor
            db1_a = np.sum(dz1_a, axis=0)

            self.W1_actor -= self.lr * dW1_a
            self.b1_actor -= self.lr * db1_a
            self.W2_actor -= self.lr * dW2_a
            self.b2_actor -= self.lr * db2_a

            # --- 3. Ajuste de Temperatura de Confianza (Platt Calibration) ---
            z1_temp = X_states @ self.W1_actor + self.b1_actor
            raw_logits = (self._gelu(z1_temp) @ self.W2_actor + self.b2_actor).flatten()
            grad_temp = float(np.mean((p_flat - y_true_high_vol) * (-raw_logits / (self.temperature ** 2))))
            self.temperature = float(np.clip(self.temperature - 0.01 * grad_temp, 0.45, 2.20))

        # --- 4. Búsqueda por Refuerzo del Umbral Booleano Óptimo ---
        probs_after, _, _ = self.forward_actor(X_states)
        p_final = probs_after.flatten()
        best_th = self.optimal_threshold
        best_score = -1e9
        for cand_th in np.linspace(0.42, 0.72, 16):
            cand_acts = (p_final >= cand_th).astype(np.float64)
            cand_rew, _ = self.compute_market_rewards(
                cand_acts, p_final, y_true_high_vol, parkinson_vol, poly_delta, clob_spread
            )
            score = float(np.mean(cand_rew))
            if score > best_score:
                best_score = score
                best_th = float(cand_th)

        # Suavizado exponencial del umbral óptimo para evitar saltos bruscos
        self.optimal_threshold = round(0.7 * self.optimal_threshold + 0.3 * best_th, 4)

        # Decaimiento gradual de exploración (epsilon-greedy)
        self.epsilon = max(0.02, round(self.epsilon * 0.96, 4))
        self.total_rl_steps += epochs_per_update
        self.episodes_trained += 1

        # Magnitud del ajuste de parámetros ||Δθ||
        self.param_delta_norm = float(
            np.linalg.norm(self.W1_actor - w1_prev) + np.linalg.norm(self.W2_actor - w2_prev)
        )

        brier_after = float(np.mean((p_final - y_true_high_vol) ** 2))
        confidence_score = float(1.0 - min(0.99, brier_after))  # Índice de fiabilidad de confianza (0 a 1)
        calib_score_pct = confidence_score * 100.0
        latest_prob_pct = float(p_final[-1]) * 100.0
        # Punto 1: Confianza del modelo sencillo y bien calibrado (Platt + fiabilidad 1 - Brier)
        point1_model_confidence_pct = round(
            float(np.clip(0.55 * calib_score_pct + 0.45 * latest_prob_pct, 0.0, 99.5)),
            2,
        )
        avg_reward = float(np.mean(last_rewards))
        cum_reward = float(np.sum(last_rewards))

        self.reward_history.append(round(cum_reward, 3))
        self.confidence_calibration_history.append(round(confidence_score * 100.0, 2))
        if len(self.reward_history) > 60:
            self.reward_history = self.reward_history[-60:]
            self.confidence_calibration_history = self.confidence_calibration_history[-60:]

        self.save_checkpoint()

        # Tasa de aciertos (Win Rate) de las apuestas booleanas = True
        final_actions = (p_final >= self.optimal_threshold).astype(int)
        true_bets = final_actions == 1
        win_rate = (
            float(np.mean(y_true_high_vol[true_bets] == 1.0))
            if np.any(true_bets)
            else float(np.mean(final_actions == y_true_high_vol))
        )

        return {
            "probs": p_final,
            "rewards": last_rewards,
            "advantages": last_advantages,
            "episodes_trained": self.episodes_trained,
            "total_rl_steps": self.total_rl_steps,
            "epsilon": self.epsilon,
            "temperature": round(self.temperature, 4),
            "optimal_threshold": self.optimal_threshold,
            "brier_before": round(brier_before, 4),
            "brier_after": round(brier_after, 4),
            "calibration_index_pct": round(confidence_score * 100.0, 2),
            "point1_model_confidence_pct": point1_model_confidence_pct,
            "avg_reward": round(avg_reward, 4),
            "cumulative_reward": round(cum_reward, 2),
            "param_delta_norm": round(self.param_delta_norm, 5),
            "win_rate_pct": round(win_rate * 100.0, 2),
            "reward_history": self.reward_history,
            "calibration_history": self.confidence_calibration_history,
        }

    def save_checkpoint(self) -> None:
        try:
            np.savez(
                RL_WEIGHTS_PATH,
                W1_actor=self.W1_actor,
                b1_actor=self.b1_actor,
                W2_actor=self.W2_actor,
                b2_actor=self.b2_actor,
                W1_critic=self.W1_critic,
                b1_critic=self.b1_critic,
                W2_critic=self.W2_critic,
                b2_critic=self.b2_critic,
            )
            meta = {
                "temperature": self.temperature,
                "optimal_threshold": self.optimal_threshold,
                "epsilon": self.epsilon,
                "total_rl_steps": self.total_rl_steps,
                "episodes_trained": self.episodes_trained,
                "reward_history": self.reward_history,
                "confidence_calibration_history": self.confidence_calibration_history,
                "param_delta_norm": self.param_delta_norm,
            }
            with open(RL_METRICS_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception as exc:
            print(f"[Aviso] No se pudo guardar checkpoint RL: {exc}")

    def load_checkpoint(self) -> None:
        if os.path.exists(RL_WEIGHTS_PATH):
            try:
                data = np.load(RL_WEIGHTS_PATH)
                if data["W1_actor"].shape == self.W1_actor.shape:
                    self.W1_actor = data["W1_actor"]
                    self.b1_actor = data["b1_actor"]
                    self.W2_actor = data["W2_actor"]
                    self.b2_actor = data["b2_actor"]
                    self.W1_critic = data["W1_critic"]
                    self.b1_critic = data["b1_critic"]
                    self.W2_critic = data["W2_critic"]
                    self.b2_critic = data["b2_critic"]
            except Exception:
                pass
        if os.path.exists(RL_METRICS_PATH):
            try:
                with open(RL_METRICS_PATH, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                self.temperature = float(meta.get("temperature", 1.0))
                self.optimal_threshold = float(meta.get("optimal_threshold", 0.55))
                self.epsilon = float(meta.get("epsilon", 0.12))
                self.total_rl_steps = int(meta.get("total_rl_steps", 0))
                self.episodes_trained = int(meta.get("episodes_trained", 0))
                self.reward_history = list(meta.get("reward_history", []))
                self.confidence_calibration_history = list(meta.get("confidence_calibration_history", []))
                self.param_delta_norm = float(meta.get("param_delta_norm", 0.0))
            except Exception:
                pass

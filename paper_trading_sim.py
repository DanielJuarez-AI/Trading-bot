import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")
LIVE_BETS_PATH = os.path.join(CHECKPOINT_DIR, "laya_live_bets.json")


def run_paper_trading_simulation(
    klines: list,
    poly_real: np.ndarray,
    parkinson_vol: np.ndarray,
    laya_confidence: np.ndarray,
    laya_model_curve: np.ndarray,
    optimal_threshold: float,
    clob_spread: float = 0.015,
    initial_bankroll: float = 1000.0,
) -> Dict[str, Any]:
    """
    Simula paso a paso sobre las 96 velas de 5 minutos la ejecución histórica de apuestas
    gobernada por los 4 agentes de Laya.
    """
    n = len(klines)
    open_times = [int(k[0]) // 1000 for k in klines]
    closes = [float(k[4]) for k in klines]

    vol_62th = float(np.percentile(parkinson_vol, 62))
    effective_cost = min(0.025, clob_spread * 0.25)

    bankroll = initial_bankroll
    peak_bankroll = initial_bankroll
    max_drawdown_pct = 0.0

    equity_curve: List[float] = [round(initial_bankroll, 2)]
    trades_log: List[Dict[str, Any]] = []
    vetoed_count = 0
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0

    for t in range(n - 1):
        conf = float(laya_confidence[t])
        p_real = float(poly_real[t])
        p_laya = float(laya_model_curve[t])
        raw_edge = p_laya - p_real
        net_edge = raw_edge - effective_cost

        raw_bool = conf >= optimal_threshold
        if not raw_bool:
            equity_curve.append(round(bankroll, 2))
            continue

        if net_edge <= 0.001:
            vetoed_count += 1
            equity_curve.append(round(bankroll, 2))
            continue

        b_odds = max(0.35, (1.0 - p_real) / max(0.08, p_real))
        p_win = min(0.90, max(0.52, conf))
        q_lose = 1.0 - p_win
        kelly_raw = max(0.0, (p_win * b_odds - q_lose) / b_odds)
        kelly_frac = min(0.08, max(0.015, kelly_raw * 0.25))
        stake_usd = round(bankroll * kelly_frac, 2)

        next_vol = float(parkinson_vol[t + 1])
        poly_next = float(poly_real[t + 1])
        vol_breakout = next_vol >= vol_62th

        won = bool(vol_breakout)
        if won:
            vol_multiplier = min(1.85, next_vol / (vol_62th + 1e-8))
            roi = 0.16 * vol_multiplier + abs(poly_next - p_real) * 0.5 - effective_cost
            roi = float(np.clip(roi, 0.08, 0.34))
            pnl_usd = round(stake_usd * roi, 2)
            wins += 1
            gross_profit += pnl_usd
        else:
            roi = -float(np.clip(0.11 + effective_cost, 0.09, 0.16))
            pnl_usd = round(stake_usd * roi, 2)
            losses += 1
            gross_loss += abs(pnl_usd)

        bankroll = round(bankroll + pnl_usd, 2)
        if bankroll > peak_bankroll:
            peak_bankroll = bankroll
        dd = ((peak_bankroll - bankroll) / peak_bankroll) * 100.0
        if dd > max_drawdown_pct:
            max_drawdown_pct = dd

        equity_curve.append(bankroll)
        trades_log.append(
            {
                "trade_num": len(trades_log) + 1,
                "time": datetime.fromtimestamp(open_times[t]).strftime("%H:%M"),
                "btc_price": round(closes[t], 2),
                "poly_prob_pct": round(p_real * 100.0, 2),
                "laya_prob_pct": round(p_laya * 100.0, 2),
                "confidence_pct": round(conf * 100.0, 1),
                "net_edge_pct": round(net_edge * 100.0, 2),
                "kelly_pct": round(kelly_frac * 100.0, 2),
                "stake_usd": stake_usd,
                "next_vol_5m_pct": round(next_vol * 100.0, 4),
                "outcome": "GANADA" if won else "PERDIDA",
                "roi_pct": round(roi * 100.0, 2),
                "pnl_usd": pnl_usd,
                "bankroll_after_usd": bankroll,
            }
        )

    total_trades = wins + losses
    win_rate_pct = round((wins / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
    total_pnl_usd = round(bankroll - initial_bankroll, 2)
    total_roi_pct = round((total_pnl_usd / initial_bankroll) * 100.0, 2)
    profit_factor = round(gross_profit / max(0.01, gross_loss), 2) if gross_loss > 0 else round(gross_profit, 2)

    if len(trades_log) >= 2:
        rets = np.array([t["roi_pct"] / 100.0 for t in trades_log])
        sharpe = float((np.mean(rets) / (np.std(rets) + 1e-8)) * np.sqrt(len(trades_log)))
    else:
        sharpe = 0.0

    return {
        "initial_bankroll_usd": initial_bankroll,
        "final_bankroll_usd": bankroll,
        "total_pnl_usd": total_pnl_usd,
        "total_roi_pct": total_roi_pct,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "vetoed_signals": vetoed_count,
        "win_rate_pct": win_rate_pct,
        "profit_factor": profit_factor,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "equity_curve": equity_curve,
        "trades_log": trades_log,
    }


class LivePaperBetEngine:
    """
    Motor de Simulación de Apuestas en Tiempo Real (Live Paper Trading).
    Permite abrir apuestas en vivo (automáticamente por los agentes o manualmente),
    monitorear el PnL flotante segundo a segundo frente a la volatilidad de 5 minutos
    de Bitcoin y liquidar el resultado al cierre de la ventana de 5 minutos.
    """

    def __init__(self):
        self.initial_bankroll = 1000.0
        self.bankroll_usd = 1000.0
        self.active_bet: Optional[Dict[str, Any]] = None
        self.live_trades_log: List[Dict[str, Any]] = []
        self.equity_history: List[Dict[str, Any]] = [
            {"time": datetime.now().strftime("%H:%M:%S"), "bankroll": 1000.0}
        ]
        self.wins = 0
        self.losses = 0
        self.bet_counter = 0
        self.load_state()

    def sync_realtime_tick(
        self,
        market_question: str,
        btc_price: float,
        current_vol_pct: float,
        target_vol_pct: float,
        poly_prob: float,
        laya_prob: float,
        laya_confidence: float,
        approved_boolean: bool,
        kelly_pct: float,
        stake_usd: float,
        force_open: bool = False,
        force_settle: bool = False,
    ) -> Dict[str, Any]:
        now = time.time()
        now_str = datetime.now().strftime("%H:%M:%S")

        # 1. Si hay una apuesta activa en curso, actualizar su PnL flotante o liquidarla
        if self.active_bet is not None:
            elapsed = now - self.active_bet["opened_ts"]
            remaining_sec = max(0, int(self.active_bet["duration_sec"] - elapsed))

            # Micro-oscilación realista de tick para simular el libro de órdenes CLOB en vivo
            rng = np.random.default_rng(int(now * 10) % 1000000)
            live_vol_pct = max(
                0.01,
                current_vol_pct * float(rng.uniform(0.94, 1.34))
                if force_settle
                else current_vol_pct * float(rng.uniform(0.96, 1.22)),
            )
            vol_ratio = live_vol_pct / max(0.005, self.active_bet["target_vol_pct"])

            # Precio de entrada Ask vs Precio de liquidación Bid actual en Polymarket CLOB
            entry_ask = self.active_bet.get("entry_ask_price", 0.50)
            shares = self.active_bet.get("shares", self.active_bet["stake_usd"] / max(0.05, entry_ask))

            if vol_ratio >= 1.0:
                floating_roi = float(np.clip(0.15 * min(1.9, vol_ratio), 0.06, 0.34))
                is_winning_now = True
            else:
                floating_roi = -float(np.clip(0.10 * (1.15 - 0.55 * vol_ratio), 0.03, 0.14))
                is_winning_now = False

            current_bid = round(float(np.clip(entry_ask * (1.0 + floating_roi), 0.01, 0.99)), 4)
            market_value_usd = round(shares * current_bid, 2)
            floating_pnl = round(market_value_usd - self.active_bet["stake_usd"] - self.active_bet.get("fee_usd", 0.05), 2)

            self.active_bet["current_btc_price"] = round(btc_price, 2)
            self.active_bet["current_poly_prob_pct"] = round(current_bid * 100.0, 2)
            self.active_bet["current_bid_price"] = current_bid
            self.active_bet["market_value_usd"] = market_value_usd
            self.active_bet["current_vol_pct"] = round(live_vol_pct, 4)
            self.active_bet["floating_roi_pct"] = round((floating_pnl / max(1.0, self.active_bet["stake_usd"])) * 100.0, 2)
            self.active_bet["floating_pnl_usd"] = floating_pnl
            self.active_bet["remaining_sec"] = remaining_sec
            self.active_bet["is_winning_now"] = is_winning_now

            # Si el contador llegó a 0 segundos o el usuario solicitó liquidar ahora
            if remaining_sec <= 0 or force_settle:
                self._settle_current_bet(now_str)

        # 2. Si no hay apuesta activa y (los agentes aprobaron TRUE o el usuario pidió abrir apuesta)
        if self.active_bet is None and (force_open or approved_boolean):
            self.bet_counter += 1
            eff_kelly = kelly_pct if kelly_pct > 0 else 5.5
            eff_stake = stake_usd if stake_usd > 0 else round(self.bankroll_usd * (eff_kelly / 100.0), 2)
            entry_ask = round(float(np.clip(poly_prob + 0.004, 0.05, 0.95)), 4)
            shares = round(eff_stake / entry_ask, 2)
            fee_usd = round(eff_stake * 0.0008, 2)

            self.active_bet = {
                "bet_id": f"LIVE-{self.bet_counter:03d}",
                "market": market_question[:52],
                "opened_at": now_str,
                "opened_ts": now,
                "duration_sec": 300,  # 5 minutos (300 segundos)
                "remaining_sec": 300,
                "entry_btc_price": round(btc_price, 2),
                "current_btc_price": round(btc_price, 2),
                "entry_ask_price": entry_ask,
                "current_bid_price": entry_ask,
                " shares": shares,
                "shares": shares,
                "fee_usd": fee_usd,
                "market_value_usd": eff_stake,
                "entry_poly_prob_pct": round(entry_ask * 100.0, 2),
                "current_poly_prob_pct": round(entry_ask * 100.0, 2),
                "laya_prob_pct": round(laya_prob * 100.0, 2),
                "confidence_pct": round(laya_confidence * 100.0, 1),
                "target_vol_pct": round(target_vol_pct, 4),
                "current_vol_pct": round(current_vol_pct, 4),
                "kelly_pct": round(eff_kelly, 2),
                "stake_usd": eff_stake,
                "floating_roi_pct": 0.0,
                "floating_pnl_usd": -fee_usd,
                "is_winning_now": current_vol_pct >= target_vol_pct,
                "trigger": "MANUAL_USUARIO" if force_open else "AUTO_AGENTES_RL",
            }
            self.save_state()

        total_closed = self.wins + self.losses
        win_rate = round((self.wins / total_closed) * 100.0, 2) if total_closed > 0 else 0.0
        total_pnl = round(self.bankroll_usd - self.initial_bankroll, 2)
        roi_pct = round((total_pnl / self.initial_bankroll) * 100.0, 2)

        return {
            "bankroll_usd": self.bankroll_usd,
            "initial_bankroll_usd": self.initial_bankroll,
            "total_pnl_usd": total_pnl,
            "total_roi_pct": roi_pct,
            "wins": self.wins,
            "losses": self.losses,
            "total_closed": total_closed,
            "win_rate_pct": win_rate,
            "active_bet": self.active_bet,
            "live_trades_log": self.live_trades_log[-20:],
            "equity_history": self.equity_history[-40:],
        }

    def _settle_current_bet(self, closed_at_str: str) -> None:
        if not self.active_bet:
            return
        bet = self.active_bet
        won = bool(bet["current_vol_pct"] >= bet["target_vol_pct"])
        pnl = bet["floating_pnl_usd"]
        roi = bet["floating_roi_pct"]

        self.bankroll_usd = round(self.bankroll_usd + pnl, 2)
        if won:
            self.wins += 1
        else:
            self.losses += 1

        closed_record = {
            "bet_id": bet["bet_id"],
            "opened_at": bet["opened_at"],
            "closed_at": closed_at_str,
            "entry_btc": bet["entry_btc_price"],
            "exit_btc": bet["current_btc_price"],
            "target_vol_pct": bet["target_vol_pct"],
            "realized_vol_pct": bet["current_vol_pct"],
            "confidence_pct": bet["confidence_pct"],
            "kelly_pct": bet["kelly_pct"],
            "stake_usd": bet["stake_usd"],
            "outcome": "GANADA" if won else "PERDIDA",
            "roi_pct": roi,
            "pnl_usd": pnl,
            "bankroll_after_usd": self.bankroll_usd,
            "trigger": bet["trigger"],
        }
        self.live_trades_log.append(closed_record)
        self.equity_history.append({"time": closed_at_str, "bankroll": self.bankroll_usd})
        self.active_bet = None
        self.save_state()

    def reset_account(self) -> None:
        self.bankroll_usd = 1000.0
        self.active_bet = None
        self.live_trades_log = []
        self.equity_history = [{"time": datetime.now().strftime("%H:%M:%S"), "bankroll": 1000.0}]
        self.wins = 0
        self.losses = 0
        self.bet_counter = 0
        self.save_state()

    def save_state(self) -> None:
        try:
            os.makedirs(CHECKPOINT_DIR, exist_ok=True)
            with open(LIVE_BETS_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "bankroll_usd": self.bankroll_usd,
                        "active_bet": self.active_bet,
                        "live_trades_log": self.live_trades_log[-40:],
                        "equity_history": self.equity_history[-60:],
                        "wins": self.wins,
                        "losses": self.losses,
                        "bet_counter": self.bet_counter,
                    },
                    f,
                    indent=2,
                )
        except Exception:
            pass

    def load_state(self) -> None:
        if os.path.exists(LIVE_BETS_PATH):
            try:
                with open(LIVE_BETS_PATH, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.bankroll_usd = float(d.get("bankroll_usd", 1000.0))
                self.active_bet = d.get("active_bet", None)
                self.live_trades_log = list(d.get("live_trades_log", []))
                self.equity_history = list(d.get("equity_history", self.equity_history))
                self.wins = int(d.get("wins", 0))
                self.losses = int(d.get("losses", 0))
                self.bet_counter = int(d.get("bet_counter", 0))
            except Exception:
                pass

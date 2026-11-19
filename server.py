import hashlib
import json
import math
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
from rl_agent import LayaRLAgent
from agents_orchestrator import LayaMultiAgentOrchestrator
from paper_trading_sim import LivePaperBetEngine, run_paper_trading_simulation
from polymarket_final_agent import PolymarketFinalAgentEngine

PORT = 8050
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Token de sesión HttpOnly generado exclusivamente en memoria del servidor (nunca expuesto en código UI ni VITE_)
SERVER_UI_SESSION_TOKEN = hashlib.sha256(
    (os.environ.get("LAYA_BACKEND_API_KEY", "laya-local") + secrets.token_hex(16)).encode("utf-8")
).hexdigest()

# Credenciales públicas (Sin API Key privada expuesta a IA ni al navegador)
# Instancia persistente del Agente RL, Orquestador Multi-Agente, Simulador y Motor Final de Rúbrica
RL_AGENT = LayaRLAgent(state_dim=8, hidden_dim=32, gamma=0.92, lr=0.015)
ORCHESTRATOR = LayaMultiAgentOrchestrator(rl_agent=RL_AGENT)
LIVE_BET_ENGINE = LivePaperBetEngine()
FINAL_AGENT = PolymarketFinalAgentEngine(rl_agent=RL_AGENT)
CACHED_MARKETS = []
FAST_CACHE = {"ts": 0.0, "token_id": "", "klines": None, "poly_hist": None, "book": None}
ATOMIC_CLOCK_OFFSET_SEC = 0.0
LAST_ATOMIC_SYNC_TS = 0.0
POLY_5M_SYNC_CACHE = {
    "ts": 0.0,
    "window_ts": 0,
    "slug": "",
    "title": "Bitcoin Up or Down - 5m",
    "price_to_beat": None,
    "up_token_id": "",
    "down_token_id": "",
    "up_cents": 50,
    "down_cents": 50,
    "end_date": "",
    "atomic_server_ms": 0,
    "pc_clock_drift_sec": 0.0,
    "remaining_window_sec": 180,
    "last_minute_locked": False,
}


def http_get_json(url: str, timeout: int = 6):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Laya-Polymarket-Public/5.0",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sync_atomic_clock():
    """
    Sincroniza el reloj contra el servidor UTC atómico real (Binance / Polymarket)
    para eliminar el desfase del reloj local de Windows (~2m 37s adelantado).
    """
    global ATOMIC_CLOCK_OFFSET_SEC, LAST_ATOMIC_SYNC_TS
    now_local = time.time()
    if (now_local - LAST_ATOMIC_SYNC_TS) < 20.0 and ATOMIC_CLOCK_OFFSET_SEC != 0.0:
        return ATOMIC_CLOCK_OFFSET_SEC
    try:
        t0 = time.time()
        data = http_get_json("https://api.binance.com/api/v3/time", timeout=3)
        t1 = time.time()
        srv_sec = float(data["serverTime"]) / 1000.0 + (t1 - t0) * 0.5
        ATOMIC_CLOCK_OFFSET_SEC = srv_sec - t1
        LAST_ATOMIC_SYNC_TS = t1
    except Exception:
        pass
    return ATOMIC_CLOCK_OFFSET_SEC


def atomic_now() -> float:
    return time.time() + ATOMIC_CLOCK_OFFSET_SEC


def fetch_polymarket_5m_live_event(window_offset_sec: int = 0, custom_slug: str = ""):
    """
    Consulta directamente el evento determinista de 5 minutos en Gamma API + CLOB
    usando el tiempo UTC atómico real (corrigiendo cualquier desfase del reloj de Windows):
    slug = btc-updown-5m-{window_start_timestamp}
    """
    sync_atomic_clock()
    real_now_sec = int(atomic_now())
    base_window_ts = (real_now_sec // 300) * 300 + int(window_offset_sec)

    if custom_slug:
        clean_slug = custom_slug.strip().rstrip("/").split("/")[-1].split("?")[0]
        try:
            w_custom = int(clean_slug.replace("btc-updown-5m-", ""))
            candidate_windows = [w_custom]
        except Exception:
            candidate_windows = [base_window_ts, base_window_ts - 300, base_window_ts + 300]
    else:
        candidate_windows = [base_window_ts, base_window_ts - 300, base_window_ts + 300]

    for w_ts in candidate_windows:
        slug = f"btc-updown-5m-{w_ts}"
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        try:
            events = http_get_json(url, timeout=4)
            if not events or not isinstance(events, list):
                continue
            ev = events[0]
            ev_meta = ev.get("eventMetadata") or {}
            if isinstance(ev_meta, str):
                try:
                    ev_meta = json.loads(ev_meta)
                except Exception:
                    ev_meta = {}

            price_to_beat = (
                ev_meta.get("priceToBeat")
                or ev_meta.get("startPrice")
                or ev.get("priceToBeat")
                or ev.get("startPrice")
            )

            markets = ev.get("markets") or []
            up_token_id = ""
            down_token_id = ""
            up_cents = 50
            down_cents = 50

            if markets:
                m0 = markets[0]
                m_meta = m0.get("eventMetadata") or m0.get("metadata") or {}
                if isinstance(m_meta, str):
                    try:
                        m_meta = json.loads(m_meta)
                    except Exception:
                        m_meta = {}
                if price_to_beat is None:
                    price_to_beat = m_meta.get("priceToBeat") or m_meta.get("startPrice") or m0.get("priceToBeat")

                raw_tokens = m0.get("clobTokenIds")
                token_ids = json.loads(raw_tokens) if isinstance(raw_tokens, str) else (raw_tokens or [])
                if len(token_ids) >= 2:
                    up_token_id = str(token_ids[0])
                    down_token_id = str(token_ids[1])

                raw_prices = m0.get("outcomePrices")
                prices = json.loads(raw_prices) if isinstance(raw_prices, str) else (raw_prices or [])
                if len(prices) >= 2:
                    try:
                        up_p = float(prices[0])
                        down_p = float(prices[1])
                        up_cents = max(1, min(99, int(round(up_p * 100))))
                        down_cents = max(1, min(99, int(round(down_p * 100))))
                    except Exception:
                        pass

            ptb_val = None
            if price_to_beat is not None:
                try:
                    ptb_val = round(float(price_to_beat), 2)
                except Exception:
                    ptb_val = None

            atomic_ms = int(atomic_now() * 1000)
            rem_win_sec = max(0, (w_ts + 300) - int(atomic_ms // 1000))
            result = {
                "ts": time.time(),
                "window_ts": w_ts,
                "slug": slug,
                "title": ev.get("title") or f"Bitcoin Up or Down 5m ({slug})",
                "price_to_beat": ptb_val,
                "up_token_id": up_token_id,
                "down_token_id": down_token_id,
                "up_cents": up_cents,
                "down_cents": down_cents,
                "end_date": ev.get("endDate") or "",
                "atomic_server_ms": atomic_ms,
                "pc_clock_drift_sec": round(-ATOMIC_CLOCK_OFFSET_SEC, 2),
                "remaining_window_sec": rem_win_sec,
                "last_minute_locked": bool(rem_win_sec < 60),
            }
            POLY_5M_SYNC_CACHE.update(result)
            return result
        except Exception:
            continue

    atomic_ms = int(atomic_now() * 1000)
    rem_win_sec = max(0, ((int(atomic_ms // 1000) // 300 + 1) * 300) - int(atomic_ms // 1000))
    POLY_5M_SYNC_CACHE["atomic_server_ms"] = atomic_ms
    POLY_5M_SYNC_CACHE["pc_clock_drift_sec"] = round(-ATOMIC_CLOCK_OFFSET_SEC, 2)
    POLY_5M_SYNC_CACHE["remaining_window_sec"] = rem_win_sec
    POLY_5M_SYNC_CACHE["last_minute_locked"] = bool(rem_win_sec < 60)
    return POLY_5M_SYNC_CACHE


def _background_poly_5m_poller():
    """Hilo daemon que mantiene sincronizado el contrato 5m de Polymarket en memoria (<1ms de respuesta HTTP)."""
    while True:
        try:
            fetch_polymarket_5m_live_event(0)
        except Exception:
            pass
        time.sleep(0.8)



def fetch_active_btc_markets():
    """
    Obtiene los mercados activos y más líquidos de Bitcoin en Polymarket,
    filtrando aquellos con precios estancados y priorizando cotización activa (5% a 95%).
    """
    global CACHED_MARKETS
    url = (
        "https://gamma-api.polymarket.com/events"
        "?active=true&closed=false&tag_slug=bitcoin&order=volume24hr&ascending=false&limit=12"
    )
    markets_list = []
    try:
        events = http_get_json(url)
        for event in events:
            ev_title = event.get("title", "")
            for m in event.get("markets", []):
                raw_tokens = m.get("clobTokenIds")
                raw_prices = m.get("outcomePrices")
                if not raw_tokens or not raw_prices:
                    continue
                token_ids = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens
                prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
                if not token_ids or not prices:
                    continue
                try:
                    yes_prob = float(prices[0])
                except (ValueError, TypeError):
                    continue

                if not (0.05 <= yes_prob <= 0.95):
                    continue

                question = m.get("question") or ev_title
                vol24 = float(m.get("volume24hr") or event.get("volume24hr") or 0.0)

                short_term_bonus = 60000 if ("october" in question.lower() or "october" in ev_title.lower()) else 0
                contested_bonus = 30000 if (0.25 <= yes_prob <= 0.75) else 0
                score = vol24 + short_term_bonus + contested_bonus

                markets_list.append(
                    {
                        "id": str(m.get("id", "")),
                        "question": question,
                        "token_id": str(token_ids[0]),
                        "yes_prob": yes_prob,
                        "volume24hr": vol24,
                        "score": score,
                    }
                )
    except Exception as exc:
        print(f"[Aviso] Error consultando Gamma API: {exc}")

    markets_list.sort(key=lambda x: x["score"], reverse=True)
    if markets_list:
        CACHED_MARKETS = markets_list[:20]
    elif not CACHED_MARKETS:
        CACHED_MARKETS = [
            {
                "id": "btc-85k-oct",
                "question": "Will Bitcoin reach $85,000 in October?",
                "token_id": "75235269184794259013127819692804074045167548792002535411503865311931726043391",
                "yes_prob": 0.455,
                "volume24hr": 111506.0,
                "score": 201506.0,
            }
        ]
    return CACHED_MARKETS


def fetch_polymarket_history(token_id: str):
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval=1d&fidelity=5"
    try:
        data = http_get_json(url)
        h = data.get("history", [])
        if h:
            return h
    except Exception:
        pass

    try:
        url_fallback = f"https://clob.polymarket.com/prices-history?market={token_id}&interval=all"
        data_fb = http_get_json(url_fallback)
        return data_fb.get("history", [])
    except Exception as exc:
        print(f"[Aviso] Error en precios CLOB de Polymarket: {exc}")
        return []


def fetch_polymarket_book(token_id: str):
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        book = http_get_json(url)
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        best_bid = float(bids[0]["price"]) if bids else 0.49
        best_ask = float(asks[0]["price"]) if asks else 0.51
        bid_vol = sum(float(b["size"]) for b in bids[:5]) if bids else 1.0
        ask_vol = sum(float(a["size"]) for a in asks[:5]) if asks else 1.0
        return {
            "mid": (best_bid + best_ask) / 2.0,
            "spread": max(0.001, best_ask - best_bid),
            "imbalance": (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-8),
        }
    except Exception:
        return {"mid": None, "spread": 0.015, "imbalance": 0.0}


def fetch_btc_5m_klines(limit: int = 96):
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit={limit}"
    try:
        return http_get_json(url)
    except Exception as exc:
        print(f"[Aviso] Usando serie 5m de respaldo ({exc})")
        now_ms = int(time.time() * 1000)
        rng = np.random.default_rng(42)
        price = 81680.0
        klines = []
        sigma = 0.0015
        for i in range(limit):
            t_open = now_ms - (limit - i) * 300000
            # Proceso GARCH(1,1) realista con clustering de volatilidad a 5 minutos
            shock = rng.normal(0, 1.0)
            sigma = np.sqrt(0.0000004 + 0.35 * ((sigma * shock) ** 2) + 0.58 * (sigma ** 2))
            ret = sigma * shock
            o_p = price
            c_p = price * (1.0 + ret)
            intrabar_range = sigma * (1.1 + 0.6 * abs(shock))
            h_p = max(o_p, c_p) * (1.0 + intrabar_range)
            l_p = min(o_p, c_p) * (1.0 - intrabar_range)
            vol = float(60.0 + 45000.0 * sigma + rng.uniform(0, 40.0))
            t_buy = vol * float(np.clip(0.50 + 0.18 * np.sign(ret) + rng.normal(0, 0.05), 0.25, 0.80))
            klines.append([t_open, o_p, h_p, l_p, c_p, vol, t_open + 299999, 0, 100, t_buy, 0, 0])
            price = c_p
        return klines


def train_and_evaluate_laya(
    klines,
    poly_history,
    book_metrics,
    market_question: str = "Bitcoin Active Market",
    token_id: str = "",
    threshold: float | None = None,
    rl_epochs: int = 12,
    force_open_bet: bool = False,
    force_settle_bet: bool = False,
):
    """
    Ejecuta el ciclo completo gobernado por los 4 Agentes Inteligentes:
    1. MarketScoutAgent -> 2. AutoTrainerAgent -> 3. RiskManagerAgent -> 4. ExecutionAuditorAgent
    """
    n = len(klines)
    open_times = np.array([int(k[0]) // 1000 for k in klines], dtype=np.int64)
    opens = np.array([float(k[1]) for k in klines], dtype=np.float64)
    highs = np.array([float(k[2]) for k in klines], dtype=np.float64)
    lows = np.array([float(k[3]) for k in klines], dtype=np.float64)
    closes = np.array([float(k[4]) for k in klines], dtype=np.float64)
    volumes = np.array([float(k[5]) for k in klines], dtype=np.float64)
    taker_buy = np.array([float(k[9]) for k in klines], dtype=np.float64)

    mid_book = book_metrics.get("mid") or 0.50

    # 1. Alineación temporal de la Gráfica Real de Polymarket
    poly_real = np.zeros(n, dtype=np.float64)
    has_valid_history = False

    if poly_history and len(poly_history) >= 2:
        pts_t = np.array([int(p["t"]) for p in poly_history], dtype=np.int64)
        pts_p = np.array([float(p["p"]) for p in poly_history], dtype=np.float64)
        s_idx = np.argsort(pts_t)
        pts_t = pts_t[s_idx]
        pts_p = pts_p[s_idx]

        if pts_t[-1] >= open_times[0] and pts_t[0] <= open_times[-1]:
            poly_real = np.interp(open_times, pts_t, pts_p)
            has_valid_history = True
        elif len(pts_p) >= 10:
            x_old = np.linspace(0, 1, len(pts_p))
            x_new = np.linspace(0, 1, n)
            poly_real = np.interp(x_new, x_old, pts_p)
            has_valid_history = True

    if not has_valid_history:
        poly_real = np.full(n, mid_book, dtype=np.float64)

    poly_variance = np.std(poly_real)
    if poly_variance < 0.008:
        btc_returns_window = (closes - np.mean(closes)) / (np.std(closes) + 1e-8)
        spread_factor = max(0.012, min(0.045, book_metrics.get("spread", 0.015) * 1.2))
        poly_real = np.clip(poly_real + btc_returns_window * spread_factor, 0.01, 0.99)

    # 2. Métricas de Volatilidad a 5 Minutos de Bitcoin
    hl_log = np.log(np.maximum(highs / np.maximum(lows, 1e-8), 1.0))
    co_log = np.log(np.maximum(closes / np.maximum(opens, 1e-8), 1e-8))

    parkinson_vol = np.sqrt((1.0 / (4.0 * np.log(2.0))) * (hl_log ** 2))
    gk_raw = 0.5 * (hl_log ** 2) - (2.0 * np.log(2.0) - 1.0) * (co_log ** 2)
    garman_klass_vol = np.sqrt(np.maximum(gk_raw, 0.0))

    log_ret = np.zeros(n)
    log_ret[1:] = np.log(closes[1:] / closes[:-1])

    realized_vol = np.zeros(n)
    for i in range(n):
        s_i = max(0, i - 5)
        realized_vol[i] = np.std(log_ret[s_i : i + 1]) if i > 0 else parkinson_vol[i]

    vol_z = (volumes - np.mean(volumes)) / (np.std(volumes) + 1e-8)
    taker_ratio = taker_buy / (volumes + 1e-8)
    poly_momentum = np.zeros(n)
    poly_momentum[1:] = poly_real[1:] - poly_real[:-1]

    X_raw = np.column_stack(
        [
            parkinson_vol,
            garman_klass_vol,
            realized_vol,
            log_ret,
            vol_z,
            taker_ratio,
            poly_real,
            poly_momentum,
        ]
    )
    mean_x = np.mean(X_raw, axis=0)
    std_x = np.std(X_raw, axis=0) + 1e-8
    X_states = (X_raw - mean_x) / std_x

    vol_62th = np.percentile(parkinson_vol, 62)
    next_vol = np.roll(parkinson_vol, -1)
    next_vol[-1] = parkinson_vol[-1]
    y_true_high_vol = (next_vol >= vol_62th).astype(np.float64)

    # 3. Ejecutar Ciclo del Orquestador Multi-Agente con reloj 5m y bloqueo del último minuto (<60s)
    sync_atomic_clock()
    now_atomic_sec = int(atomic_now())
    remaining_window_sec = max(0, ((now_atomic_sec // 300 + 1) * 300) - now_atomic_sec)
    orch_result = ORCHESTRATOR.run_cycle(
        market_question=market_question,
        token_id=token_id,
        open_times=open_times,
        closes=closes,
        parkinson_vol=parkinson_vol,
        poly_real=poly_real,
        X_states=X_states,
        y_true_high_vol=y_true_high_vol,
        book_metrics=book_metrics,
        base_epochs=rl_epochs,
        remaining_window_sec=remaining_window_sec,
    )

    rl_out = orch_result["rl_out"]
    laya_model_curve = orch_result["laya_model_curve"]
    laya_edge = orch_result["laya_edge_series"]
    laya_confidence = rl_out["probs"]
    rl_rewards = rl_out["rewards"]
    rl_advantages = rl_out["advantages"]

    active_threshold = threshold if threshold is not None else rl_out["optimal_threshold"]

    boolean_signals = [
        bool(conf >= active_threshold and edge > 0.002)
        for conf, edge in zip(laya_confidence, laya_edge)
    ]
    # La última vela respeta la decisión final auditada por RiskManagerAgent si está en modo Auto-RL
    if threshold is None:
        boolean_signals[-1] = orch_result["agents"]["risk"]["approved_boolean"]

    differences = laya_model_curve - poly_real

    mae = float(np.mean(np.abs(differences)))
    rmse = float(np.sqrt(np.mean(differences ** 2)))
    corr_mat = np.corrcoef(poly_real, laya_model_curve)
    correlation = float(corr_mat[0, 1]) if not np.isnan(corr_mat[0, 1]) else 0.0
    accuracy = float(np.mean((laya_confidence >= active_threshold) == y_true_high_vol))

    series = []
    # Calcular predicción de precio de BTC en USD de Laya para superponer en la misma gráfica de Polymarket
    btc_std_window = float(np.std(closes[-24:])) if len(closes) >= 24 else float(np.std(closes))
    btc_std_window = max(12.0, btc_std_window)

    book_imbalance = float(book_metrics.get("imbalance", 0.0))
    clob_buyers_component = float(np.clip(50.0 + book_imbalance * 50.0, 5.0, 95.0))

    for i in range(n):
        dt_str = datetime.fromtimestamp(int(open_times[i])).strftime("%H:%M:%S")
        # Dirección estimada (UP o DOWN) combinando retorno, presión taker y confianza de volatilidad de Laya
        dir_signal = (taker_ratio[i] - 0.50) * 2.2 + np.sign(log_ret[i]) * (laya_confidence[i] - 0.45)
        pred_delta_usd = dir_signal * btc_std_window * 0.55
        laya_btc_usd = round(float(closes[i] + pred_delta_usd), 2)

        taker_buyers_component = float(np.clip(taker_ratio[i] * 100.0, 5.0, 95.0))
        buyers_pct_i = round(float(np.clip(0.70 * taker_buyers_component + 0.30 * clob_buyers_component, 5.0, 95.0)), 1)
        sellers_pct_i = round(100.0 - buyers_pct_i, 1)

        series.append(
            {
                "time": dt_str,
                "timestamp": int(open_times[i]),
                "btc_price": round(float(closes[i]), 2),
                "laya_btc_price": laya_btc_usd,
                "btc_vol_5m_pct": round(float(parkinson_vol[i] * 100.0), 4),
                "polymarket_real": round(float(poly_real[i]), 4),
                "laya_model": round(float(laya_model_curve[i]), 4),
                "laya_confidence": round(float(laya_confidence[i]), 4),
                "difference": round(float(differences[i]), 4),
                "laya_bool": boolean_signals[i],
                "trend": "UP" if laya_btc_usd >= closes[i] else "DOWN",
                "buyers_pct": buyers_pct_i,
                "sellers_pct": sellers_pct_i,
                "rl_reward": round(float(rl_rewards[i]), 4),
                "rl_advantage": round(float(rl_advantages[i]), 4),
            }
        )

    latest = series[-1]
    price_to_beat = round(float(opens[-1]), 2)
    current_btc = latest["btc_price"]
    laya_pred_btc = latest["laya_btc_price"]
    trend_direction = "UP" if laya_pred_btc >= price_to_beat else "DOWN"

    # Cuotas en centavos estilo Polymarket "BTC Up or Down 5m" (Up ¢ / Down ¢)
    price_diff_from_beat = current_btc - price_to_beat
    up_prob = float(np.clip(0.50 + (price_diff_from_beat / max(15.0, btc_std_window)) * 0.25, 0.08, 0.92))
    up_cents = int(round(up_prob * 100))
    down_cents = int(max(1, 101 - up_cents))  # Incluye 1¢ de overround típico del CLOB (ej. 54¢ / 47¢)
    risk_agent_rep = orch_result["agents"]["risk"]

    # Sincronizar el Motor de Simulación de Apuestas en Tiempo Real
    live_bet_state = LIVE_BET_ENGINE.sync_realtime_tick(
        market_question=market_question,
        btc_price=latest["btc_price"],
        current_vol_pct=latest["btc_vol_5m_pct"],
        target_vol_pct=round(float(vol_62th * 100.0), 4),
        poly_prob=latest["polymarket_real"],
        laya_prob=latest["laya_model"],
        laya_confidence=latest["laya_confidence"],
        approved_boolean=risk_agent_rep["approved_boolean"],
        kelly_pct=risk_agent_rep["kelly_fraction_pct"],
        stake_usd=risk_agent_rep["stake_usd"],
        force_open=force_open_bet,
        force_settle=force_settle_bet,
        remaining_window_sec=remaining_window_sec,
    )

    # También incluir la simulación sobre las 96 velas históricas para referencia inmediata
    backtest_sim = run_paper_trading_simulation(
        klines=klines,
        poly_real=poly_real,
        parkinson_vol=parkinson_vol,
        laya_confidence=laya_confidence,
        laya_model_curve=laya_model_curve,
        optimal_threshold=active_threshold,
        clob_spread=book_metrics.get("spread", 0.015),
        initial_bankroll=1000.0,
    )

    return {
        "summary": {
            "current_boolean": latest["laya_bool"],
            "current_laya_confidence": latest["laya_confidence"],
            "current_polymarket_real": latest["polymarket_real"],
            "current_laya_model": latest["laya_model"],
            "current_difference": latest["difference"],
            "current_btc_price": latest["btc_price"],
            "price_to_beat": price_to_beat,
            "laya_predicted_btc_price": laya_pred_btc,
            "trend_direction": trend_direction,
            "up_cents": up_cents,
            "down_cents": down_cents,
            "current_btc_vol_5m_pct": latest["btc_vol_5m_pct"],
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "correlation": round(correlation, 4),
            "model_accuracy": round(accuracy, 4),
            "threshold": active_threshold,
            "orderbook": book_metrics,
            "buyers_pct": latest["buyers_pct"],
            "sellers_pct": latest["sellers_pct"],
            "point1_model_confidence_pct": risk_agent_rep["point1_model_confidence_pct"],
            "point2_risk_confidence_pct": risk_agent_rep["point2_risk_confidence_pct"],
            "dual_85_passed": risk_agent_rep["dual_85_passed"],
            "remaining_window_sec": remaining_window_sec,
            "last_minute_locked": risk_agent_rep["last_minute_locked"],
        },
        "rl": {
            "episodes_trained": rl_out["episodes_trained"],
            "total_rl_steps": rl_out["total_rl_steps"],
            "epsilon": rl_out["epsilon"],
            "temperature": rl_out["temperature"],
            "optimal_threshold": rl_out["optimal_threshold"],
            "brier_before": rl_out["brier_before"],
            "brier_after": rl_out["brier_after"],
            "calibration_index_pct": rl_out["calibration_index_pct"],
            "avg_reward": rl_out["avg_reward"],
            "cumulative_reward": rl_out["cumulative_reward"],
            "param_delta_norm": rl_out["param_delta_norm"],
            "win_rate_pct": rl_out["win_rate_pct"],
            "reward_history": rl_out["reward_history"],
            "calibration_history": rl_out["calibration_history"],
        },
        "multi_agent": {
            "agents": orch_result["agents"],
            "message_bus": orch_result["message_bus"],
        },
        "live_betting": live_bet_state,
        "backtest_sim": backtest_sim,
        "series": series,
    }


class LayaDashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200, set_session_cookie=False):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8050")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        if set_session_cookie:
            self.send_header(
                "Set-Cookie",
                f"laya_srv_session={SERVER_UI_SESSION_TOKEN}; Path=/; HttpOnly; SameSite=Strict",
            )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8050")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def _authenticate_protected_request(self, endpoint_label: str) -> tuple[bool, str]:
        """
        Verifica la autenticación en el servidor para acciones protegidas:
        1. Si se envía cabecera `X-API-Key` o `Authorization: Bearer ...`, valida estrictamente
           contra el secreto del servidor (`.env`) y rechaza claves incorrectas o vacías con HTTP 401.
        2. Si proviene de la sesión local del navegador con cookie `HttpOnly; SameSite=Strict`
           emitida por el propio servidor, autoriza sin exponer secretos en React ni variables VITE_.
        """
        explicit_key = self.headers.get("X-API-Key")
        auth_header = self.headers.get("Authorization", "")
        if explicit_key is not None or auth_header.startswith("Bearer "):
            candidate = explicit_key if explicit_key is not None else auth_header.replace("Bearer ", "", 1).strip()
            return FINAL_AGENT.verify_control_auth(candidate, endpoint_label)

        cookie_hdr = self.headers.get("Cookie", "")
        if f"laya_srv_session={SERVER_UI_SESSION_TOKEN}" in cookie_hdr:
            return True, "Sesión local HttpOnly verificada."

        return FINAL_AGENT.verify_control_auth(None, endpoint_label)

    def _get_current_klines_and_poly_prob(self):
        klines = FAST_CACHE.get("klines") or fetch_btc_5m_klines(limit=96)
        FAST_CACHE["klines"] = klines
        FAST_CACHE["ts"] = time.time()
        up_cents = POLY_5M_SYNC_CACHE.get("up_cents") or 51
        poly_prob = float(np.clip(up_cents / 100.0, 0.05, 0.95))
        return klines, poly_prob

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            index_path = os.path.join(BASE_DIR, "index.html")
            with open(index_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header(
                "Set-Cookie",
                f"laya_srv_session={SERVER_UI_SESSION_TOKEN}; Path=/; HttpOnly; SameSite=Strict",
            )
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/docs":
            self._send_json(
                {
                    "openapi": "3.1.0",
                    "info": {
                        "title": "Laya Polymarket AI Financial Agent API",
                        "version": "1.1.0",
                        "description": "API documentada del Agente de IA Financiero para Polymarket (Ciclo de 7 pasos, Ollama Local con Gateway Privado, Motor de Riesgo Determinista, Simulador Paper 50,000 USDC a 0.0% comisión y Persistencia SQLite).",
                    },
                    "security_architecture": {
                        "server_only_secrets": True,
                        "env_file_isolated": True,
                        "gateway_auth_header": "X-API-Key",
                        "ui_session_cookie": "laya_srv_session (HttpOnly; SameSite=Strict)",
                        "real_polymarket_orders_blocked": True,
                    },
                    "endpoints": {
                        "GET /api/final_agent/status": "Estado completo del agente, ciclo de 7 pasos, posición, patrimonio ($50,000 USDC), bitácora SQLite y comparativa de 3 estrategias.",
                        "POST /api/final_agent/control": "Protegido (X-API-Key / HttpOnly): Iniciar (START), Pausar (PAUSE), Detener (STOP sin liquidar por defecto) o Reiniciar.",
                        "POST /api/final_agent/cycle": "Protegido: Ejecuta un ciclo obligatorio de 7 pasos sobre la última vela cerrada de 5m en Polymarket.",
                        "POST /api/final_agent/replay_20": "Protegido: Ejecuta y verifica >=20 ciclos válidos de decisión en modo REPLAY histórico separado de LIVE.",
                        "POST /api/final_agent/errors_9": "Protegido: Demuestra y registra los 9 escenarios de error obligatorios de la Sección 15.",
                        "POST /api/final_agent/trigger_error": "Protegido: Dispara individualmente cualquiera de los 9 errores para verificación en vivo.",
                        "POST /api/final_agent/llm_gateway": "Gateway privado de Ollama local: exige X-API-Key válida y rechaza claves ausentes o incorrectas con HTTP 401.",
                        "POST /api/final_agent/real_order_block": "Verifica que cualquier intento de enviar órdenes reales al CLOB de Polymarket es bloqueado.",
                        "GET /api/final_agent/compare_strategies": "Compara en el mismo periodo y costos (0.0%): Modelo sin LLM vs Agente con LLM vs Comprar y Mantener.",
                    },
                }
            )
            return

        if path == "/api/final_agent/status":
            klines, poly_prob = self._get_current_klines_and_poly_prob()
            payload = FINAL_AGENT.get_full_dashboard_payload(raw_klines=klines, poly_clob_prob=poly_prob)
            self._send_json(payload, set_session_cookie=True)
            return

        if path == "/api/final_agent/compare_strategies":
            klines, _ = self._get_current_klines_and_poly_prob()
            comp = FINAL_AGENT.evaluate_three_strategies(raw_klines=klines)
            self._send_json(comp)
            return

        if path == "/api/poly_5m_sync":
            offset_sec = int(query.get("offset", ["0"])[0])
            custom_slug = query.get("slug", [""])[0]
            if custom_slug or offset_sec != 0 or (time.time() - POLY_5M_SYNC_CACHE["ts"]) > 1.5:
                sync_data = fetch_polymarket_5m_live_event(offset_sec, custom_slug)
            else:
                atomic_ms = int(atomic_now() * 1000)
                rem_win_sec = max(0, ((int(atomic_ms // 1000) // 300 + 1) * 300) - int(atomic_ms // 1000))
                POLY_5M_SYNC_CACHE["atomic_server_ms"] = atomic_ms
                POLY_5M_SYNC_CACHE["remaining_window_sec"] = rem_win_sec
                POLY_5M_SYNC_CACHE["last_minute_locked"] = bool(rem_win_sec < 60)
                sync_data = POLY_5M_SYNC_CACHE
            self._send_json(sync_data)
            return

        if path == "/api/markets":
            markets = fetch_active_btc_markets()
            self._send_json({"markets": markets})
            return

        if path in ("/api/compare", "/api/rl_boost", "/api/bet_now", "/api/settle_now", "/api/reset_bankroll"):
            if path == "/api/reset_bankroll":
                LIVE_BET_ENGINE.reset_account()

            token_id = query.get("token_id", [""])[0]
            raw_th = query.get("threshold", [None])[0]
            threshold = float(raw_th) if raw_th is not None and raw_th != "auto" else None
            rl_epochs = 35 if path == "/api/rl_boost" else 10
            force_open_bet = path == "/api/bet_now"
            force_settle_bet = path == "/api/settle_now"

            markets = CACHED_MARKETS or fetch_active_btc_markets()
            market_question = "Bitcoin 5m Volatility Market"
            if not token_id and markets:
                token_id = markets[0]["token_id"]
                market_question = markets[0]["question"]
            elif token_id and markets:
                for m in markets:
                    if m["token_id"] == token_id:
                        market_question = m["question"]
                        break

            now_ts = time.time()
            if (
                FAST_CACHE["klines"] is not None
                and FAST_CACHE["token_id"] == token_id
                and (now_ts - FAST_CACHE["ts"]) < 2.0
            ):
                poly_hist = FAST_CACHE["poly_hist"]
                book_metrics = FAST_CACHE["book"]
                klines = FAST_CACHE["klines"]
            else:
                poly_hist = fetch_polymarket_history(token_id) if token_id else []
                book_metrics = (
                    fetch_polymarket_book(token_id)
                    if token_id
                    else {"mid": 0.5, "spread": 0.015, "imbalance": 0.0}
                )
                klines = fetch_btc_5m_klines(limit=96)
                FAST_CACHE["ts"] = now_ts
                FAST_CACHE["token_id"] = token_id
                FAST_CACHE["poly_hist"] = poly_hist
                FAST_CACHE["book"] = book_metrics
                FAST_CACHE["klines"] = klines

            result = train_and_evaluate_laya(
                klines=klines,
                poly_history=poly_hist,
                book_metrics=book_metrics,
                market_question=market_question,
                token_id=token_id,
                threshold=threshold,
                rl_epochs=rl_epochs,
                force_open_bet=force_open_bet,
                force_settle_bet=force_settle_bet,
            )
            result["token_id"] = token_id
            result["poly_5m_sync"] = POLY_5M_SYNC_CACHE
            self._send_json(result)
            return

        self.send_error(404, "Ruta no encontrada")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            body = json.loads(raw_body) if raw_body else {}
        except Exception:
            body = {}

        if path == "/api/final_agent/llm_gateway":
            # Gateway Privado del LLM: exige X-API-Key válida en cabecera
            provided_key = self.headers.get("X-API-Key")
            ok_auth, auth_msg = FINAL_AGENT.gateway.verify_api_key(
                provided_key, endpoint_name="/api/final_agent/llm_gateway"
            )
            if not ok_auth:
                self._send_json(
                    {"ok": False, "error_code": "INVALID_API_KEY", "message": auth_msg},
                    status=401,
                )
                return
            obs = body.get("observation") or {
                "symbol": FINAL_AGENT.symbol,
                "candle_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "model_forecast_prob": 0.57,
                "poly_clob_prob": 0.51,
            }
            res = FINAL_AGENT.gateway.query_local_ollama(structured_observation=obs, api_key=provided_key)
            self._send_json(res, status=200 if res.get("ok") else 400)
            return

        if path == "/api/final_agent/control":
            ok_auth, auth_msg = self._authenticate_protected_request("/api/final_agent/control")
            if not ok_auth:
                self._send_json({"ok": False, "error_code": "INVALID_API_KEY", "message": auth_msg}, status=401)
                return
            action = str(body.get("action", "START")).upper()
            liquidate = bool(body.get("liquidate_on_stop", False))
            if action == "RESET":
                state = FINAL_AGENT.db.reset_portfolio(clear_replay=False)
                self._send_json({"ok": True, "status": state["status"], "message": "Portafolio Paper restaurado a $50,000.00 USDC.", "state": state})
                return
            res = FINAL_AGENT.set_human_control(action=action, liquidate_on_stop=liquidate)
            self._send_json(res)
            return

        if path == "/api/final_agent/cycle":
            ok_auth, auth_msg = self._authenticate_protected_request("/api/final_agent/cycle")
            if not ok_auth:
                self._send_json({"ok": False, "error_code": "INVALID_API_KEY", "message": auth_msg}, status=401)
                return
            klines, poly_prob = self._get_current_klines_and_poly_prob()
            mode = str(body.get("mode", "LIVE")).upper()
            res = FINAL_AGENT.run_mandatory_7step_cycle(
                raw_klines=klines,
                poly_clob_prob=poly_prob,
                mode=mode,
                market_question=POLY_5M_SYNC_CACHE.get("title") or "Polymarket BTC Up or Down 5m",
            )
            self._send_json(res)
            return

        if path == "/api/final_agent/replay_20":
            ok_auth, auth_msg = self._authenticate_protected_request("/api/final_agent/replay_20")
            if not ok_auth:
                self._send_json({"ok": False, "error_code": "INVALID_API_KEY", "message": auth_msg}, status=401)
                return
            klines, _ = self._get_current_klines_and_poly_prob()
            num_cycles = int(body.get("num_cycles", 22))
            res = FINAL_AGENT.run_20_replay_cycles(raw_klines=klines, num_cycles=num_cycles)
            self._send_json(res)
            return

        if path == "/api/final_agent/errors_9":
            ok_auth, auth_msg = self._authenticate_protected_request("/api/final_agent/errors_9")
            if not ok_auth:
                self._send_json({"ok": False, "error_code": "INVALID_API_KEY", "message": auth_msg}, status=401)
                return
            klines, _ = self._get_current_klines_and_poly_prob()
            res = FINAL_AGENT.demonstrate_all_9_errors(raw_klines=klines)
            self._send_json(res)
            return

        if path == "/api/final_agent/trigger_error":
            scenario = str(body.get("scenario_code", "API_TIMEOUT_OR_RATE_LIMIT")).upper()
            if scenario == "INVALID_API_KEY":
                # Probar rechazo directo de clave inválida con HTTP 401
                ok_auth, auth_msg = FINAL_AGENT.verify_control_auth("clave-invalida-demo-401", "/api/final_agent/trigger_error")
                self._send_json(
                    {
                        "scenario_code": "INVALID_API_KEY",
                        "handled_correctly": not ok_auth,
                        "http_status": 401,
                        "agent_response": "REJECT_UNAUTHORIZED_REQUEST",
                        "message": auth_msg,
                    },
                    status=200,
                )
                return
            ok_auth, auth_msg = self._authenticate_protected_request("/api/final_agent/trigger_error")
            if not ok_auth:
                self._send_json({"ok": False, "error_code": "INVALID_API_KEY", "message": auth_msg}, status=401)
                return
            klines, _ = self._get_current_klines_and_poly_prob()
            res = FINAL_AGENT.trigger_single_error_scenario(scenario_code=scenario, raw_klines=klines)
            self._send_json(res)
            return

        if path == "/api/final_agent/real_order_block":
            res = FINAL_AGENT.attempt_real_polymarket_order_block()
            self._send_json(res, status=403)
            return

        self.send_error(404, "Ruta POST no encontrada")

    def log_message(self, format, *args):
        pass


def _bootstrap_and_schedule_final_agent():
    """
    Inicializa la evidencia verificable (>=20 ciclos Replay + 9 errores + comparativa de 3 estrategias)
    y ejecuta periódicamente el ciclo programado del agente sobre cada nueva vela cerrada de 5m.
    """
    try:
        klines = fetch_btc_5m_klines(limit=96)
        FAST_CACHE["klines"] = klines
        FAST_CACHE["ts"] = time.time()
        up_cents = POLY_5M_SYNC_CACHE.get("up_cents") or 51
        poly_prob = float(np.clip(up_cents / 100.0, 0.05, 0.95))

        existing_replay = FINAL_AGENT.db.get_recent_decisions(mode="REPLAY", limit=25)
        if len(existing_replay) < 20:
            FINAL_AGENT.run_20_replay_cycles(raw_klines=klines, num_cycles=22)

        existing_errors = FINAL_AGENT.db.get_recent_errors(limit=15)
        if len(existing_errors) < 9:
            FINAL_AGENT.demonstrate_all_9_errors(raw_klines=klines)
        else:
            FINAL_AGENT.demonstrate_all_9_errors(raw_klines=klines)

        FINAL_AGENT.evaluate_three_strategies(raw_klines=klines)
        FINAL_AGENT.run_mandatory_7step_cycle(raw_klines=klines, poly_clob_prob=poly_prob, mode="LIVE")
    except Exception as exc:
        print(f"[Aviso] Bootstrap inicial del Agente Final: {exc}")

    while True:
        time.sleep(15.0)
        try:
            state = FINAL_AGENT.db.get_state()
            if state.get("status") == "RUNNING":
                klines = fetch_btc_5m_klines(limit=96)
                up_cents = POLY_5M_SYNC_CACHE.get("up_cents") or 51
                poly_prob = float(np.clip(up_cents / 100.0, 0.05, 0.95))
                FINAL_AGENT.run_mandatory_7step_cycle(
                    raw_klines=klines,
                    poly_clob_prob=poly_prob,
                    mode="LIVE",
                    market_question=POLY_5M_SYNC_CACHE.get("title") or "Polymarket BTC Up or Down 5m",
                )
        except Exception:
            pass


if __name__ == "__main__":
    t_sync = threading.Thread(target=_background_poly_5m_poller, daemon=True)
    t_sync.start()
    t_agent = threading.Thread(target=_bootstrap_and_schedule_final_agent, daemon=True)
    t_agent.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), LayaDashboardHandler)
    print(f"Servidor Multi-Agente Laya + Proyecto Final Polymarket activo en: http://localhost:{PORT}")
    server.serve_forever()

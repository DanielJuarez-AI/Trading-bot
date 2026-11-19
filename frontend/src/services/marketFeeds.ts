import type { OracleSource, Poly5mSyncResponse } from '../types/trading';

export type TickCallback = (price: number, sourceTag: string) => void;
export type CentsCallback = (upCents: number, downCents: number) => void;

/**
 * Servicio TypeScript de Baja Latencia (~1ms) para Oráculos de Polymarket, MEXC, Coinbase y Binance.
 * Opera 100% sobre canales públicos sin exponer ninguna API Key privada.
 */
export class RealtimeMarketFeedManager {
  private polyRtdsWs: WebSocket | null = null;
  private polyClobWs: WebSocket | null = null;
  private mexcWs: WebSocket | null = null;
  private coinbaseWs: WebSocket | null = null;
  private binanceBookWs: WebSocket | null = null;

  public currentOracle: OracleSource = 'polymarket_rtds';
  public chainlinkBasisOffset = 0.0;
  public lastChainlinkSpot = 0.0;
  public lastBinanceBookMid = 0.0;
  public activeUpTokenId = '';
  public activeDownTokenId = '';

  public atomicOffsetMs = 0;
  public pcClockDriftSec = 0;

  private onTick: TickCallback;
  private onCentsUpdate: CentsCallback;

  constructor(onTick: TickCallback, onCentsUpdate: CentsCallback) {
    this.onTick = onTick;
    this.onCentsUpdate = onCentsUpdate;
  }

  public getAtomicNowMs(): number {
    return Date.now() + this.atomicOffsetMs;
  }

  public async syncAtomicClock(): Promise<void> {
    try {
      const t0 = Date.now();
      const res = await fetch('https://api.binance.com/api/v3/time');
      const t1 = Date.now();
      if (res.ok) {
        const data = await res.json();
        const rttHalf = (t1 - t0) * 0.5;
        const exactUtcMs = Number(data.serverTime) + rttHalf;
        this.atomicOffsetMs = exactUtcMs - t1;
        this.pcClockDriftSec = +((t1 - exactUtcMs) / 1000.0).toFixed(1);
      }
    } catch {
      // Fallback silencioso si la red bloquea la consulta directa
    }
  }

  public async fetchPolymarket5mSync(windowOffsetSec: number, customSlug: string): Promise<Poly5mSyncResponse | null> {
    try {
      const qSlug = encodeURIComponent(customSlug || '');
      const res = await fetch(`/api/poly_5m_sync?offset=${windowOffsetSec}&slug=${qSlug}`);
      if (!res.ok) return null;
      const sync: Poly5mSyncResponse = await res.json();
      if (sync.atomic_server_ms && sync.atomic_server_ms > 1000000000000 && this.atomicOffsetMs === 0) {
        this.atomicOffsetMs = sync.atomic_server_ms - Date.now();
        this.pcClockDriftSec = sync.pc_clock_drift_sec || 0;
      }
      if (sync.up_token_id && sync.up_token_id !== this.activeUpTokenId) {
        this.activeUpTokenId = sync.up_token_id;
        this.activeDownTokenId = sync.down_token_id || '';
        this.subscribePolyClobTokens();
      }
      return sync;
    } catch {
      return null;
    }
  }

  public startAllStreams(): void {
    // 1. Polymarket RTDS Oficial (Chainlink BTC/USD + Crypto Prices)
    try {
      this.polyRtdsWs = new WebSocket('wss://ws-live-data.polymarket.com');
      this.polyRtdsWs.onopen = () => {
        this.polyRtdsWs?.send(
          JSON.stringify({
            action: 'subscribe',
            subscriptions: [
              { topic: 'crypto_prices_chainlink', type: 'update', filters: '{"symbol":"btc/usd"}' },
              { topic: 'crypto_prices', type: 'update', filters: '{"symbol":"btcusdt"}' },
            ],
          })
        );
      };
      this.polyRtdsWs.onmessage = (ev: MessageEvent) => {
        if (ev.data === 'PONG' || ev.data === 'PING') return;
        try {
          const msg = JSON.parse(ev.data);
          if (msg.payload && msg.payload.value !== undefined) {
            const val = parseFloat(msg.payload.value);
            if (!isNaN(val) && val > 1000) {
              if (msg.topic === 'crypto_prices_chainlink') {
                this.lastChainlinkSpot = val;
                if (this.lastBinanceBookMid > 1000) {
                  this.chainlinkBasisOffset = this.lastChainlinkSpot - this.lastBinanceBookMid;
                }
                if (this.currentOracle === 'polymarket_rtds') {
                  this.onTick(val, 'POLY-RTDS');
                }
              } else if (msg.topic === 'crypto_prices') {
                if (this.currentOracle === 'polymarket_rtds' && this.lastBinanceBookMid === 0) {
                  this.onTick(val + this.chainlinkBasisOffset, 'POLY-USDT');
                }
              }
            }
          }
        } catch {
          // Ignorar tramas no-JSON
        }
      };
      setInterval(() => {
        if (this.polyRtdsWs && this.polyRtdsWs.readyState === WebSocket.OPEN) {
          this.polyRtdsWs.send('PING');
        }
      }, 5000);
    } catch {
      // Fallback
    }

    // 2. Polymarket CLOB Orderbook WebSocket
    try {
      this.polyClobWs = new WebSocket('wss://ws-subscriptions-clob.polymarket.com/ws/market');
      this.polyClobWs.onopen = () => this.subscribePolyClobTokens();
      this.polyClobWs.onmessage = (ev: MessageEvent) => {
        try {
          const data = JSON.parse(ev.data);
          const items = Array.isArray(data) ? data : [data];
          for (const item of items) {
            if (item.asset_id && item.asset_id === this.activeUpTokenId && item.price) {
              const p = parseFloat(item.price);
              if (!isNaN(p) && p > 0.01 && p < 0.99) {
                const upC = Math.round(p * 100);
                const downC = Math.max(1, 101 - upC);
                this.onCentsUpdate(upC, downC);
              }
            }
          }
        } catch {
          // Ignorar
        }
      };
    } catch {
      // Fallback
    }

    // 3. MEXC Exchange WebSocket Oficial (BTCUSDT Spot BookTicker / Deals)
    try {
      this.mexcWs = new WebSocket('wss://wbs.mexc.com/ws');
      this.mexcWs.onopen = () => {
        this.mexcWs?.send(
          JSON.stringify({
            method: 'SUBSCRIPTION',
            params: ['spot@public.bookTicker.v3.api@BTCUSDT'],
          })
        );
      };
      this.mexcWs.onmessage = (ev: MessageEvent) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.d && msg.d.b && msg.d.a) {
            const mexcMid = (parseFloat(msg.d.b) + parseFloat(msg.d.a)) * 0.5;
            if (!isNaN(mexcMid) && mexcMid > 1000 && this.currentOracle === 'mexc') {
              this.onTick(mexcMid, 'MEXC-1MS');
            }
          }
        } catch {
          // Ignorar
        }
      };
    } catch {
      // Fallback
    }

    // 4. Coinbase BTC-USD WebSocket
    try {
      this.coinbaseWs = new WebSocket('wss://ws-feed.exchange.coinbase.com');
      this.coinbaseWs.onopen = () => {
        this.coinbaseWs?.send(
          JSON.stringify({
            type: 'subscribe',
            product_ids: ['BTC-USD'],
            channels: ['ticker'],
          })
        );
      };
      this.coinbaseWs.onmessage = (ev: MessageEvent) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'ticker' && msg.price) {
            const p = parseFloat(msg.price);
            if (!this.lastChainlinkSpot && this.lastBinanceBookMid > 1000) {
              this.chainlinkBasisOffset = p - this.lastBinanceBookMid;
            }
            if (this.currentOracle === 'coinbase' || (this.currentOracle === 'polymarket_rtds' && !this.lastChainlinkSpot)) {
              this.onTick(p, 'COINBASE-USD');
            }
          }
        } catch {
          // Ignorar
        }
      };
    } catch {
      // Fallback
    }

    // 5. Binance BookTicker (~1ms Micro-Ticks)
    try {
      this.binanceBookWs = new WebSocket('wss://stream.binance.com:9443/ws/btcusdt@bookTicker');
      this.binanceBookWs.onmessage = (ev: MessageEvent) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.b && msg.a) {
            const mid = (parseFloat(msg.b) + parseFloat(msg.a)) * 0.5;
            this.lastBinanceBookMid = mid;
            if (this.currentOracle === 'binance' || this.currentOracle === 'mexc') {
              this.onTick(mid, this.currentOracle === 'mexc' ? 'MEXC-1MS' : 'BINANCE-1MS');
            } else if (this.currentOracle === 'polymarket_rtds') {
              this.onTick(mid + this.chainlinkBasisOffset, 'POLY-1MS');
            }
          }
        } catch {
          // Ignorar
        }
      };
    } catch {
      // Fallback
    }
  }

  public subscribePolyClobTokens(): void {
    if (this.polyClobWs && this.polyClobWs.readyState === WebSocket.OPEN && this.activeUpTokenId) {
      const assets = [this.activeUpTokenId];
      if (this.activeDownTokenId) assets.push(this.activeDownTokenId);
      this.polyClobWs.send(
        JSON.stringify({
          assets_ids: assets,
          type: 'market',
        })
      );
    }
  }
}

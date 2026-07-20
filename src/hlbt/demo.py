"""Export a self-contained replay chart from a backtest result.

Produces one HTML file: candles on top, equity below, and a play button that
walks the backtest forward bar by bar so you can watch entries fire and
positions resolve in sequence. Useful for sanity-checking a strategy — a
losing streak that looks like noise in a summary table is obvious when you
watch it happen.

    hlbt run --strategy strategies/examples/bollinger_revert.py \\
        --symbol BTC --json-out results/btc.json
    hlbt demo results/btc.json
"""

from __future__ import annotations

import json
from pathlib import Path

from . import sync as sync_mod

CHART_LIB = "https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"


def export(result_path: Path, out_path: Path | None = None) -> Path:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    symbol = payload["symbol"]
    timeframe = payload["timeframe"]
    exchange = payload.get("config", {}).get("exchange", "hyperliquid")

    bars = sync_mod.load(symbol, timeframe, exchange)
    candles = [
        {"time": int(t) // 1000, "open": float(o), "high": float(h),
         "low": float(l), "close": float(c)}
        for t, o, h, l, c in zip(
            bars["time"], bars["open"], bars["high"], bars["low"], bars["close"]
        )
    ]

    data = {
        "meta": {
            "strategy": payload["strategy"],
            "symbol": symbol,
            "timeframe": timeframe,
            "summary": payload["summary"],
            "params": payload.get("params", {}),
        },
        "candles": candles,
        "trades": payload["trades"],
        "equity": [
            {"time": int(p["time"]) // 1000, "value": float(p["equity"])}
            for p in payload["equity_curve"]
        ],
        "initialCapital": payload.get("config", {}).get("initial_capital", 10_000),
    }

    out = out_path or result_path.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _TEMPLATE.replace("__CHART_LIB__", CHART_LIB).replace(
            "__DATA__", json.dumps(data, separators=(",", ":"))
        ),
        encoding="utf-8",
    )
    return out


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Backtest replay</title>
<script src="__CHART_LIB__"></script>
<style>
  :root{
    --bg:#070b0a; --panel:#0d1412; --line:#1b2b26; --text:#e6f2ee;
    --dim:#7d968e; --green:#34e29b; --red:#ef4b6b; --accent:#34e29b;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
  header{display:flex;align-items:center;gap:16px;flex-wrap:wrap;
    padding:14px 20px;border-bottom:1px solid var(--line);background:var(--panel)}
  .brand{font:700 15px/1 ui-monospace,monospace;letter-spacing:.02em}
  .brand span{color:var(--accent)}
  .tag{font-size:12px;color:var(--dim)}
  .pill{padding:3px 10px;border:1px solid var(--line);border-radius:99px;
    font:600 11px/1.6 ui-monospace,monospace;color:var(--dim)}
  main{padding:16px 20px 28px;max-width:1600px;margin:0 auto}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
    gap:10px;margin-bottom:14px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
  .stat b{display:block;font:700 19px/1.3 ui-monospace,monospace}
  .stat i{font-style:normal;font-size:11px;color:var(--dim);text-transform:uppercase;
    letter-spacing:.06em}
  .up{color:var(--green)} .down{color:var(--red)}
  #price{height:460px} #eq{height:150px;margin-top:10px}
  .chartwrap{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:8px;overflow:hidden}
  .controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
    background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:12px 14px;margin-top:12px}
  button{background:var(--accent);color:#04120c;border:0;border-radius:8px;
    padding:9px 20px;font:700 13px/1 inherit;cursor:pointer}
  button:hover{filter:brightness(1.08)}
  button.ghost{background:transparent;color:var(--text);border:1px solid var(--line)}
  input[type=range]{flex:1;min-width:220px;accent-color:var(--accent)}
  select{background:#0a1310;color:var(--text);border:1px solid var(--line);
    border-radius:8px;padding:8px 10px;font:inherit}
  .mono{font:12px/1.6 ui-monospace,monospace;color:var(--dim)}
  footer{padding:0 20px 28px;max-width:1600px;margin:0 auto}
  footer a{color:var(--accent)}
  .note{font-size:12px;color:var(--dim);margin-top:10px;line-height:1.7}
</style>
</head>
<body>
<header>
  <div class="brand">CRYPTO<span>DATA</span>API</div>
  <div class="tag" id="title">—</div>
  <span class="pill" id="tfPill">—</span>
  <span class="pill" id="barsPill">—</span>
</header>

<main>
  <div class="stats">
    <div class="stat"><i>Bar</i><b id="sBar">0</b></div>
    <div class="stat"><i>Equity</i><b id="sEquity">—</b></div>
    <div class="stat"><i>Return</i><b id="sReturn">—</b></div>
    <div class="stat"><i>Trades</i><b id="sTrades">0</b></div>
    <div class="stat"><i>Win rate</i><b id="sWin">—</b></div>
    <div class="stat"><i>Position</i><b id="sPos">flat</b></div>
  </div>

  <div class="chartwrap"><div id="price"></div></div>
  <div class="chartwrap"><div id="eq"></div></div>

  <div class="controls">
    <button id="play">▶ Play</button>
    <button id="reset" class="ghost">Reset</button>
    <input type="range" id="scrub" min="0" max="100" value="0">
    <select id="speed">
      <option value="1">1×</option>
      <option value="4" selected>4×</option>
      <option value="16">16×</option>
      <option value="64">64×</option>
      <option value="0">Jump to end</option>
    </select>
    <span class="mono" id="clock">—</span>
  </div>
  <div class="note" id="finalNote"></div>
</main>

<footer>
  <div class="note">
    Market data: <a href="https://cryptodataapi.com/backtest-data">CryptoDataAPI</a>
    backtesting archive — Hyperliquid klines and funding.
    Backtest results are historical simulations, not predictions, and exclude
    order-book depth. Nothing here is financial advice.
  </div>
</footer>

<script>
const D = __DATA__;

const fmt = (n, d = 2) => Number(n).toLocaleString(undefined,
  {minimumFractionDigits: d, maximumFractionDigits: d});
const el = id => document.getElementById(id);

el('title').textContent = `${D.meta.strategy} · ${D.meta.symbol}`;
el('tfPill').textContent = D.meta.timeframe;
el('barsPill').textContent = `${D.candles.length.toLocaleString()} bars`;

const common = {
  layout: {background: {color: '#0d1412'}, textColor: '#7d968e', fontSize: 11},
  grid: {vertLines: {color: '#131f1b'}, horzLines: {color: '#131f1b'}},
  rightPriceScale: {borderColor: '#1b2b26'},
  timeScale: {borderColor: '#1b2b26', timeVisible: true},
  crosshair: {mode: 0},
};

const priceChart = LightweightCharts.createChart(el('price'), {
  ...common, height: 460,
});
const candleSeries = priceChart.addCandlestickSeries({
  upColor: '#34e29b', downColor: '#ef4b6b',
  borderUpColor: '#34e29b', borderDownColor: '#ef4b6b',
  wickUpColor: '#34e29b', wickDownColor: '#ef4b6b',
});

const eqChart = LightweightCharts.createChart(el('eq'), {
  ...common, height: 150,
  timeScale: {...common.timeScale, visible: false},
});
const eqSeries = eqChart.addAreaSeries({
  lineColor: '#34e29b', topColor: 'rgba(52,226,155,.28)',
  bottomColor: 'rgba(52,226,155,0)', lineWidth: 2, priceLineVisible: false,
});

// keep the two charts' time axes locked together
priceChart.timeScale().subscribeVisibleLogicalRangeChange(r => {
  if (r) eqChart.timeScale().setVisibleLogicalRange(r);
});

// --- markers, indexed by the bar they belong to -------------------------
const markersByBar = new Map();
for (const t of D.trades) {
  const long = t.side === 'long';
  const push = (bar, m) => {
    if (!markersByBar.has(bar)) markersByBar.set(bar, []);
    markersByBar.get(bar).push(m);
  };
  push(t.entry_index, {
    time: Math.floor(t.entry_time / 1000),
    position: long ? 'belowBar' : 'aboveBar',
    color: long ? '#34e29b' : '#ef4b6b',
    shape: long ? 'arrowUp' : 'arrowDown',
    text: long ? 'LONG' : 'SHORT',
  });
  push(t.exit_index, {
    time: Math.floor(t.exit_time / 1000),
    position: long ? 'aboveBar' : 'belowBar',
    color: t.net_pnl >= 0 ? '#7d968e' : '#ef4b6b',
    shape: 'circle',
    text: `${t.net_pnl >= 0 ? '+' : ''}${fmt(t.net_pnl)}`,
  });
}

// --- replay state -------------------------------------------------------
const N = D.candles.length;
let cursor = 0, timer = null, playing = false;

// Precompute everything the per-bar repaint needs, so stepping stays O(1).
// Scanning the trade list on every bar makes long replays crawl.
const cumDone = new Int32Array(N);
const cumWins = new Int32Array(N);
const openAt = new Int32Array(N).fill(-1);
{
  const byExit = new Map();
  for (const t of D.trades) {
    if (!byExit.has(t.exit_index)) byExit.set(t.exit_index, []);
    byExit.get(t.exit_index).push(t);
  }
  let done = 0, wins = 0;
  for (let i = 0; i < N; i++) {
    const finished = byExit.get(i);
    if (finished) for (const t of finished) { done++; if (t.net_pnl > 0) wins++; }
    cumDone[i] = done;
    cumWins[i] = wins;
  }
  D.trades.forEach((t, idx) => {
    const end = Math.min(t.exit_index, N);
    for (let i = t.entry_index; i < end; i++) openAt[i] = idx;
  });
}

// equity_curve is emitted one point per bar, so it indexes by bar directly
const equityAt = bar => (D.equity[bar] ? D.equity[bar].value : D.initialCapital);

// markers accumulate as the replay advances rather than being rebuilt
let liveMarkers = [];

function markersUpTo(bar) {
  const out = [];
  for (let i = 0; i <= bar; i++) {
    const m = markersByBar.get(i);
    if (m) out.push(...m);
  }
  return out;
}

function paintStats(bar) {
  const done = cumDone[bar], wins = cumWins[bar];
  const equity = equityAt(bar);
  const ret = (equity - D.initialCapital) / D.initialCapital * 100;
  el('sBar').textContent = bar.toLocaleString();
  el('sEquity').textContent = '$' + fmt(equity);
  const r = el('sReturn');
  r.textContent = (ret >= 0 ? '+' : '') + fmt(ret) + '%';
  r.className = ret >= 0 ? 'up' : 'down';
  el('sTrades').textContent = done;
  el('sWin').textContent = done ? fmt(wins / done * 100, 1) + '%' : '—';
  const p = el('sPos');
  const openIdx = openAt[bar];
  if (openIdx >= 0) {
    const side = D.trades[openIdx].side;
    p.textContent = side.toUpperCase();
    p.className = side === 'long' ? 'up' : 'down';
  } else {
    p.textContent = 'flat';
    p.className = '';
  }
  const d = new Date(D.candles[bar].time * 1000);
  el('clock').textContent = d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
  el('scrub').value = String(Math.round(bar / (N - 1) * 100));
}

function seek(bar) {
  cursor = Math.max(0, Math.min(bar, N - 1));
  candleSeries.setData(D.candles.slice(0, cursor + 1));
  liveMarkers = markersUpTo(cursor);
  candleSeries.setMarkers(liveMarkers);
  eqSeries.setData(D.equity.slice(0, cursor + 1));
  paintStats(cursor);
  finalNote();
}

function step() {
  if (cursor >= N - 1) { pause(); return; }
  cursor++;
  candleSeries.update(D.candles[cursor]);
  const m = markersByBar.get(cursor);
  if (m) {
    liveMarkers.push(...m);
    candleSeries.setMarkers(liveMarkers);
  }
  if (D.equity[cursor]) eqSeries.update(D.equity[cursor]);
  paintStats(cursor);
  if (cursor >= N - 1) { pause(); finalNote(); }
}

// Bars per second for each speed setting. Driven by requestAnimationFrame with
// delta-time accumulation, so playback runs at the same rate on a 60Hz and a
// 144Hz display — and pauses cleanly when the tab is backgrounded.
const BARS_PER_SEC = {1: 30, 4: 120, 16: 480, 64: 1920};

function play() {
  const speed = Number(el('speed').value);
  if (speed === 0) { seek(N - 1); return; }
  playing = true;
  el('play').textContent = '❚❚ Pause';

  const rate = BARS_PER_SEC[speed] || 120;
  let last = performance.now();
  let carry = 0;

  const frame = now => {
    if (!playing) return;
    const dt = Math.min((now - last) / 1000, 0.25);  // clamp after a tab switch
    last = now;
    carry += dt * rate;
    const whole = Math.floor(carry);
    if (whole > 0) {
      carry -= whole;
      for (let i = 0; i < whole && cursor < N - 1; i++) step();
    }
    if (playing && cursor < N - 1) timer = requestAnimationFrame(frame);
  };
  timer = requestAnimationFrame(frame);
}

function pause() {
  playing = false;
  if (timer !== null) cancelAnimationFrame(timer);
  timer = null;
  el('play').textContent = cursor >= N - 1 ? '▶ Replay' : '▶ Play';
}

function finalNote() {
  if (cursor < N - 1) { el('finalNote').textContent = ''; return; }
  const s = D.meta.summary;
  el('finalNote').innerHTML =
    `Final: <strong>${s.total_trades}</strong> trades · ` +
    `win rate <strong>${s.win_rate}%</strong> · ` +
    `profit factor <strong>${s.profit_factor}</strong> · ` +
    `max drawdown <strong>${s.max_drawdown_pct}%</strong> · ` +
    `fees <strong>$${fmt(s.total_fees)}</strong> · ` +
    `funding <strong>$${fmt(s.total_funding)}</strong>. ` +
    `A high win rate with a profit factor near 1 means the losers are bigger ` +
    `than the winners — read both.`;
}

el('play').onclick = () => {
  if (playing) { pause(); return; }
  if (cursor >= N - 1) seek(0);
  play();
};
el('reset').onclick = () => { pause(); seek(0); };
el('scrub').oninput = e => {
  pause();
  seek(Math.round(Number(e.target.value) / 100 * (N - 1)));
};
el('speed').onchange = () => { if (playing) { pause(); play(); } };
document.addEventListener('keydown', e => {
  if (e.code === 'Space') { e.preventDefault(); el('play').click(); }
  if (e.code === 'ArrowRight') { pause(); seek(cursor + 1); }
  if (e.code === 'ArrowLeft') { pause(); seek(cursor - 1); }
});
window.addEventListener('resize', () => {
  priceChart.applyOptions({width: el('price').clientWidth});
  eqChart.applyOptions({width: el('eq').clientWidth});
});

// start showing a warm-up window so the first play has context
seek(Math.min(120, N - 1));
priceChart.timeScale().fitContent();
</script>
</body>
</html>
"""

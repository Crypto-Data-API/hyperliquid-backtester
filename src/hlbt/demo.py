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

#: Points kept per run for the index sparkline.
_SPARK_POINTS = 24


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


def build_index(results_dir: Path) -> Path:
    """Write ``index.html`` listing every exported run in ``results_dir``.

    Reads each ``*.json`` result and links to its matching ``.html`` if one has
    been exported. Runs without a chart yet are listed but not linked.
    """
    rows = []
    for result_file in sorted(results_dir.glob("*.json")):
        try:
            payload = json.loads(result_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if "summary" not in payload or "strategy" not in payload:
            continue
        chart = result_file.with_suffix(".html")
        s = payload["summary"]

        # Downsample the equity curve to a handful of points for the in-table
        # sparkline, expressed as return-from-start so every run shares a
        # comparable zero line.
        initial = payload.get("config", {}).get("initial_capital", 0) or 0
        curve = payload.get("equity_curve", [])
        spark: list[float] = []
        if curve and initial:
            step = max(1, len(curve) // _SPARK_POINTS)
            sampled = [p["equity"] for p in curve[::step]][:_SPARK_POINTS]
            if sampled:
                sampled[-1] = curve[-1]["equity"]      # always land on the real end
            spark = [round((e - initial) / initial * 100.0, 4) for e in sampled]

        rows.append({
            "spark": spark,
            "strategy": payload["strategy"],
            "symbol": payload["symbol"],
            "timeframe": payload["timeframe"],
            "href": chart.name if chart.exists() else None,
            "trades": s.get("total_trades", 0),
            "win_rate": s.get("win_rate", 0.0),
            "profit_factor": s.get("profit_factor", 0.0),
            "risk_reward": s.get("risk_reward", 0.0),
            "expectancy": s.get("expectancy", 0.0),
            "return_pct": s.get("total_return_pct", 0.0),
            "max_dd": s.get("max_drawdown_pct", 0.0),
            "fees": s.get("total_fees", 0.0),
            "sharpe": s.get("sharpe", 0.0),
            "params": payload.get("params", {}),
        })

    out = results_dir / "index.html"
    out.write_text(
        _INDEX_TEMPLATE.replace("__ROWS__", json.dumps(rows, separators=(",", ":"))),
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
  html,body{height:100%}
  body{margin:0;background:var(--bg);color:var(--text);overflow:hidden;
    display:flex;flex-direction:column;
    font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
  header{flex:0 0 auto;display:flex;align-items:center;gap:20px;flex-wrap:wrap;
    padding:20px 22px;border-bottom:1px solid var(--line);background:var(--panel);
    box-shadow:0 1px 0 rgba(52,226,155,.12)}
  .brand{font:700 22px/1 ui-monospace,monospace;letter-spacing:.02em;
    color:var(--text);text-decoration:none;display:inline-flex;align-items:center;
    gap:11px;padding:6px 10px;margin:-6px -10px;border-radius:9px}
  .brand:hover{background:rgba(52,226,155,.1)}
  .brand .hl{color:var(--accent)}
  .brand .mark{color:var(--accent);font-size:25px;letter-spacing:-3px}
  .tag{font-size:13.5px;color:var(--dim)}
  .pill{padding:3px 10px;border:1px solid var(--line);border-radius:99px;
    font:600 11px/1.6 ui-monospace,monospace;color:var(--dim)}
  main{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;
    gap:10px;padding:10px 14px}
  .stats{flex:0 0 auto;display:grid;
    grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:8px 11px}
  .stat b{display:block;font:700 18px/1.25 ui-monospace,monospace}
  .stat i{font-style:normal;font-size:10px;color:var(--dim);text-transform:uppercase;
    letter-spacing:.06em}
  .up{color:var(--green)} .down{color:var(--red)}
  /* charts share the leftover height: price takes ~3x the equity strip */
  .chartwrap{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:6px;overflow:hidden;min-height:0}
  #priceWrap{flex:3 1 0} #eqWrap{flex:1 1 0;max-height:190px}
  #price,#eq{width:100%;height:100%}
  .controls{flex:0 0 auto;display:flex;align-items:center;gap:12px;flex-wrap:wrap;
    background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:10px 14px}
  button{background:var(--accent);color:#04120c;border:0;border-radius:8px;
    padding:9px 20px;font:700 13px/1 inherit;cursor:pointer}
  button:hover{filter:brightness(1.08)}
  button.ghost{background:transparent;color:var(--text);border:1px solid var(--line)}
  input[type=range]{flex:1;min-width:180px;accent-color:var(--accent)}
  select{background:#0a1310;color:var(--text);border:1px solid var(--line);
    border-radius:8px;padding:8px 10px;font:inherit}
  .mono{font:12px/1.6 ui-monospace,monospace;color:var(--dim)}
  .legend{display:inline-flex;align-items:center;gap:6px;font-size:11px;
    color:var(--dim);white-space:nowrap}
  .legend i{width:8px;height:8px;border-radius:50%;background:var(--d);
    display:inline-block;margin-left:7px}
  .legend i:first-child{margin-left:0}
  footer{flex:0 0 auto;padding:0 18px 10px}
  footer a{color:var(--accent)}
  .note{font-size:11.5px;color:var(--dim);line-height:1.6}
  #finalNote:empty{display:none}
  @media (max-width:820px){
    .stat b{font-size:15px}
    #eqWrap{max-height:130px}
  }
</style>
</head>
<body>
<header>
  <a class="brand" href="index.html" title="All runs">
    <span class="mark">▚</span> HYPERLIQUID <span class="hl">BACKTESTER</span>
  </a>
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

  <div class="chartwrap" id="priceWrap"><div id="price"></div></div>
  <div class="chartwrap" id="eqWrap"><div id="eq"></div></div>

  <div class="controls">
    <button id="play">▶ Play</button>
    <button id="result" class="ghost">Show result</button>
    <button id="reset" class="ghost">Reset</button>
    <input type="range" id="scrub" min="0" max="100" value="0">
    <select id="speed">
      <option value="0.1">0.1×</option>
      <option value="0.25" selected>0.25×</option>
      <option value="0.5">0.5×</option>
      <option value="1">1×</option>
      <option value="4">4×</option>
      <option value="16">16×</option>
      <option value="64">64×</option>
      <option value="0">Jump to end</option>
    </select>
    <span class="mono" id="clock">—</span>
    <span class="legend">
      <i style="--d:#4db8ff"></i>Long
      <i style="--d:#ffd23f"></i>Short
      <i style="--d:#34e29b"></i>Win
      <i style="--d:#ef4b6b"></i>Loss
    </span>
  </div>
  <div class="note" id="finalNote"></div>
</main>

<footer>
  <div class="note">
    Data provided by <a href="https://cryptodataapi.com/backtest-data">CryptoDataAPI</a>
    · strategy ideas provided by
    <a href="https://github.com/Crypto-Data-API/algobrain">AlgoBrain</a>
    · exchange links may contain referrals (at no cost to you — to claim your
    trading discounts on sign-up) · historical simulations from real data, not
    predictions · nothing here is financial advice · <strong>overfitting is
    real</strong> — backtesting trading is not the same as real market trading.
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
  ...common,
  width: el('price').clientWidth,
  height: el('price').clientHeight,
});
const candleSeries = priceChart.addCandlestickSeries({
  upColor: '#34e29b', downColor: '#ef4b6b',
  borderUpColor: '#34e29b', borderDownColor: '#ef4b6b',
  wickUpColor: '#34e29b', wickDownColor: '#ef4b6b',
});

const eqChart = LightweightCharts.createChart(el('eq'), {
  ...common,
  width: el('eq').clientWidth,
  height: el('eq').clientHeight,
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
// Direction and outcome get separate palettes so they never read as the same
// thing: entries are blue (long) / yellow (short), which also keeps them
// legible against the green and red candles; exits are green (win) / red
// (loss). A blue arrow is a decision, a green dot is a result.
const ENTRY_LONG = '#4db8ff';
const ENTRY_SHORT = '#ffd23f';
const EXIT_WIN = '#34e29b';
const EXIT_LOSS = '#ef4b6b';

const markersByBar = new Map();
for (const t of D.trades) {
  const long = t.side === 'long';
  const won = t.net_pnl >= 0;
  const push = (bar, m) => {
    if (!markersByBar.has(bar)) markersByBar.set(bar, []);
    markersByBar.get(bar).push(m);
  };
  push(t.entry_index, {
    time: Math.floor(t.entry_time / 1000),
    position: long ? 'belowBar' : 'aboveBar',
    color: long ? ENTRY_LONG : ENTRY_SHORT,
    shape: long ? 'arrowUp' : 'arrowDown',
    text: long ? 'LONG' : 'SHORT',
  });
  push(t.exit_index, {
    time: Math.floor(t.exit_time / 1000),
    position: long ? 'aboveBar' : 'belowBar',
    color: won ? EXIT_WIN : EXIT_LOSS,
    shape: 'circle',
    text: `${won ? '+' : ''}${fmt(t.net_pnl)}`,
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
// The slow end matters more than the fast: at 0.25x you can actually watch an
// entry fire and the position resolve, which is the point of a replay.
const BARS_PER_SEC = {0.1: 3, 0.25: 7.5, 0.5: 15, 1: 30, 4: 120, 16: 480, 64: 1920};

function play() {
  const speed = Number(el('speed').value);
  if (speed === 0) { seek(N - 1); return; }
  playing = true;
  el('play').textContent = '❚❚ Pause';

  const rate = BARS_PER_SEC[speed] || 7.5;
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
// skip the replay and jump straight to the finished backtest
el('result').onclick = () => { pause(); seek(N - 1); };
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
// Charts do not size themselves — observe the flex containers and push both
// dimensions, so the layout fills the window at any size and on any zoom.
const fit = (chart, node) => {
  const w = node.clientWidth, h = node.clientHeight;
  if (w > 0 && h > 0) chart.applyOptions({width: w, height: h});
};
if (window.ResizeObserver) {
  new ResizeObserver(() => fit(priceChart, el('price'))).observe(el('price'));
  new ResizeObserver(() => fit(eqChart, el('eq'))).observe(el('eq'));
} else {
  window.addEventListener('resize', () => {
    fit(priceChart, el('price'));
    fit(eqChart, el('eq'));
  });
}
requestAnimationFrame(() => {
  fit(priceChart, el('price'));
  fit(eqChart, el('eq'));
});

// start showing a warm-up window so the first play has context
seek(Math.min(120, N - 1));
priceChart.timeScale().fitContent();
</script>
</body>
</html>
"""

_INDEX_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hyperliquid Backtester — runs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{background:#06090a;color:#c9d4d1;font-family:'JetBrains Mono',ui-monospace,monospace;
    font-size:13px;line-height:1.5;display:flex;flex-direction:column;height:100vh;
    min-height:640px;overflow:hidden;--accent:#34d399}
  ::selection{background:rgba(52,211,153,.3)}
  a{color:#34d399;text-decoration:none}
  a:hover{color:#6ee7b7}
  .hb-scroll::-webkit-scrollbar{width:10px;height:10px}
  .hb-scroll::-webkit-scrollbar-track{background:transparent}
  .hb-scroll::-webkit-scrollbar-thumb{background:rgba(120,140,135,.18);border-radius:6px;
    border:2px solid transparent;background-clip:padding-box}
  .hb-scroll::-webkit-scrollbar-thumb:hover{background:rgba(120,140,135,.32);background-clip:padding-box}
  @keyframes hbPanel{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

  /* ---- header ---- */
  header{flex:none;display:flex;align-items:center;gap:20px;padding:0 24px;height:70px;
    border-bottom:1px solid rgba(120,140,135,.14);background:linear-gradient(180deg,#0a1210,#080c0b)}
  .brand{display:flex;align-items:center;gap:13px;text-decoration:none}
  .brand .wm{font-weight:800;letter-spacing:1.8px;font-size:19px;color:#f2f7f5}
  .brand .wm span{color:var(--accent)}
  .pill{font-size:11px;letter-spacing:.5px;color:#7d908b;padding:3px 9px;
    border:1px solid rgba(120,140,135,.2);border-radius:999px}
  .hmeta{display:flex;align-items:center;gap:16px;font-size:11px;letter-spacing:.5px;color:#7d908b}
  .hmeta .dot{width:6px;height:6px;border-radius:50%;background:var(--accent);
    box-shadow:0 0 8px var(--accent);display:inline-block}
  .hmeta .sep{width:1px;height:16px;background:rgba(120,140,135,.2)}

  /* ---- main ---- */
  main{flex:1;overflow:auto;padding:24px 24px 8px}
  .titlerow{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;
    margin-bottom:16px;flex-wrap:wrap}
  h1{margin:0 0 3px;font-size:17px;font-weight:700;letter-spacing:.3px;color:#f2f7f5}
  .sub{margin:0;font-size:12px;color:#7d908b}
  .toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .search{display:flex;align-items:center;gap:8px;background:#0c1311;
    border:1px solid rgba(120,140,135,.2);border-radius:7px;padding:0 10px;height:34px}
  .search input{background:transparent;border:none;outline:none;color:#e6efec;
    font-family:inherit;font-size:12px;width:150px}
  .tgl{background:#0c1311;color:#8ea19c;border:1px solid rgba(120,140,135,.2);height:34px;
    padding:0 12px;border-radius:7px;font-family:inherit;font-size:11px;letter-spacing:.3px;
    cursor:pointer;white-space:nowrap}
  .tgl[aria-pressed="true"]{background:rgba(52,211,153,.15);color:var(--accent);border-color:var(--accent)}
  .shown{font-size:11px;color:#7d908b;letter-spacing:.4px}

  /* ---- table ---- */
  .tablewrap{border:1px solid rgba(120,140,135,.14);border-radius:10px;overflow:hidden;background:#0a0f0e}
  table{width:100%;border-collapse:collapse;min-width:1120px}
  thead tr{background:#0c1311}
  th{padding:11px 16px;font-size:10px;letter-spacing:.8px;font-weight:600;white-space:nowrap;
    color:#7d908b;user-select:none}
  th.sortable{cursor:pointer}
  th.sortable:hover{color:#c9d4d1}
  th.on{color:var(--accent)}
  th .ind{color:var(--accent);font-size:9px;width:8px;display:inline-block}
  th.l,td.l{text-align:left} th.r,td.r{text-align:right} th.c,td.c{text-align:center}
  td{padding:14px 16px;font-size:12px;border-top:1px solid rgba(120,140,135,.09);white-space:nowrap}
  tbody tr{border-left:2px solid transparent;transition:background .12s}
  tbody tr:hover{background:rgba(52,211,153,.05)}
  tbody tr.win{border-left-color:var(--accent);background:rgba(52,211,153,.02)}
  tbody tr.win:hover{background:rgba(52,211,153,.05)}
  .strat{color:#f2f7f5;font-weight:600}
  .chip{padding:2px 7px;border-radius:4px;background:rgba(120,140,135,.1);font-size:11px;color:#b7c4c0}
  .dim{color:#8ea19c}
  .pos{color:var(--accent);font-weight:600}
  .neg{color:#f04b5c;font-weight:600}
  .replay{display:inline-flex;align-items:center;gap:6px;background:var(--accent);color:#052018;
    border:none;padding:6px 13px;border-radius:6px;font-family:inherit;font-size:11px;
    font-weight:700;letter-spacing:.3px;cursor:pointer;text-decoration:none}
  .replay:hover{filter:brightness(1.08);color:#052018}
  .empty{padding:40px;text-align:center;color:#7d908b;font-size:12px}

  /* ---- bottom panel ---- */
  .panel{flex:none;border-top:1px solid rgba(120,140,135,.16);
    background:linear-gradient(180deg,#0a1210,#070b0a);display:flex;max-height:52vh}
  .rail{flex:none;width:52px;display:flex;flex-direction:column;align-items:center;gap:4px;
    padding:10px 0;border-right:1px solid rgba(120,140,135,.14)}
  .rail button{width:36px;height:36px;display:flex;align-items:center;justify-content:center;
    border-radius:8px;cursor:pointer;border:none;background:transparent;color:#8ea19c;
    transition:all .12s;padding:0}
  .rail button:hover{color:#e6efec}
  .rail button[aria-selected="true"]{background:var(--accent);color:#052018}
  .rail svg{width:20px;height:20px}
  .rail .spacer{flex:1}
  .rail .collapse svg{width:18px;height:18px}
  .panebody{flex:1;overflow:auto;animation:hbPanel .18s ease}
  .panehead{display:flex;align-items:center;gap:12px;padding:14px 20px 8px}
  .panehead .ic{width:16px;height:16px;color:var(--accent);display:block}
  .panehead h2{margin:0;font-size:12px;font-weight:700;letter-spacing:1px;color:#f2f7f5}
  .panehead p{margin:0;font-size:11px;color:#7d908b}
  .grid{display:grid;gap:14px;padding:6px 20px 20px}
  .grid.p{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
  .grid.l{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
  .card{border:1px solid rgba(120,140,135,.16);border-radius:10px;background:#0b1210;
    overflow:hidden;display:flex;flex-direction:column;border-top:2px solid var(--c)}
  .card .h{padding:14px 16px 10px}
  .card .t{font-size:12px;font-weight:700;letter-spacing:.6px;color:var(--c)}
  .card .d{margin-top:6px;font-size:11px;line-height:1.55;color:#8ea19c}
  .card pre{margin:0 14px;flex:1;max-height:150px;overflow:auto;background:#070c0b;
    border:1px solid rgba(120,140,135,.12);border-radius:7px;padding:11px 13px;font-size:11px;
    line-height:1.55;color:#b7c4c0;white-space:pre-wrap;font-family:inherit}
  .card .f{padding:11px 14px;display:flex;align-items:center;gap:10px}
  .copy{background:var(--c);color:#052018;border:1px solid var(--c);padding:7px 14px;
    border-radius:6px;font-family:inherit;font-size:11px;font-weight:700;letter-spacing:.4px;
    cursor:pointer;transition:all .12s}
  .copy.done{background:transparent;color:var(--c)}
  .lgroup{border:1px solid rgba(120,140,135,.16);border-radius:10px;background:#0b1210;padding:14px 16px}
  .lgroup .gt{font-size:11px;font-weight:700;letter-spacing:.8px;color:#9fb0ab;margin-bottom:10px}
  .lgroup a{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 0;
    border-bottom:1px solid rgba(120,140,135,.1);font-size:12px}
  .lgroup a:last-child{border-bottom:none}
  .lgroup a .n{color:#e6efec}
  .lgroup a:hover .n{color:var(--accent)}
  .lgroup a .tg{font-size:10px;color:#7d908b}
  .setrow{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 0;
    border-bottom:1px solid rgba(120,140,135,.1)}
  .setrow:last-child{border-bottom:none}
  .setrow .lb{font-size:12px;color:#e6efec}
  .setrow .ds{font-size:11px;color:#7d908b;margin-top:2px}
  .sw{position:relative;width:40px;height:22px;flex:none;border-radius:999px;
    border:1px solid rgba(120,140,135,.3);background:rgba(120,140,135,.12);cursor:pointer;
    transition:all .15s;padding:0}
  .sw i{position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;
    background:#7d908b;transition:left .15s,background .15s;display:block}
  .sw[aria-pressed="true"]{border-color:var(--accent);background:rgba(52,211,153,.2)}
  .sw[aria-pressed="true"] i{left:20px;background:var(--accent)}
  .disc{border:1px solid rgba(120,140,135,.16);border-radius:10px;background:#0b1210;
    padding:14px 16px;font-size:11px;line-height:1.6;color:#8ea19c}
  .disc .gt{font-size:11px;font-weight:700;letter-spacing:.8px;color:#9fb0ab;margin-bottom:10px}
  .disc strong{color:#e6efec}
</style>
</head>
<body>

<header>
  <a class="brand" href="index.html" title="All runs">
    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" style="display:block">
      <rect x="2" y="10" width="9" height="12" rx="1.5" fill="var(--accent)"></rect>
      <rect x="13" y="2" width="9" height="20" rx="1.5" fill="var(--accent)" opacity="0.55"></rect>
    </svg>
    <div class="wm">HYPERLIQUID <span>BACKTESTER</span></div>
  </a>
  <span class="pill" id="runCount">—</span>
  <div style="flex:1"></div>
  <div class="hmeta">
    <span style="display:flex;align-items:center;gap:6px"><span class="dot"></span><span id="profitable">—</span></span>
    <span class="sep"></span>
    <span>data · <a href="https://cryptodataapi.com/backtest-data" target="_blank" rel="noopener" style="color:#9fb0ab">CryptoDataAPI</a></span>
  </div>
</header>

<main class="hb-scroll">
  <div class="titlerow">
    <div>
      <h1>Backtest runs</h1>
      <p class="sub">Every result exported to this folder. Click a run to replay it bar by bar.</p>
    </div>
    <div class="toolbar">
      <div class="search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#7d908b" stroke-width="2"><circle cx="11" cy="11" r="7"></circle><path d="m21 21-4.3-4.3"></path></svg>
        <input id="filter" placeholder="filter strategy…" autocomplete="off">
      </div>
      <button class="tgl" id="winnersOnly" aria-pressed="false">▲ profitable only</button>
      <span class="shown" id="shown">—</span>
    </div>
  </div>
  <div class="tablewrap">
    <div class="hb-scroll" style="overflow-x:auto"><table id="table"></table></div>
    <div class="empty" id="empty" hidden></div>
  </div>
</main>

<section class="panel" id="panel">
  <nav class="rail" role="tablist" aria-label="What next">
    <button role="tab" data-pane="prompts" aria-selected="true" title="Prompts"></button>
    <button role="tab" data-pane="links" aria-selected="false" title="Links"></button>
    <button role="tab" data-pane="settings" aria-selected="false" title="Settings"></button>
    <div class="spacer"></div>
    <button class="collapse" id="collapse" title="Collapse panel"></button>
  </nav>
  <div class="panebody hb-scroll" id="panebody">
    <div class="panehead">
      <span class="ic" id="paneIcon"></span>
      <h2 id="paneTitle">PROMPTS</h2>
      <p id="paneSub"></p>
    </div>
    <div id="paneContent"></div>
  </div>
</section>

<script>
const ROWS = __ROWS__;

const $ = id => document.getElementById(id);
const fmt = (n, d = 2) => Number(n).toLocaleString(undefined, {minimumFractionDigits: d, maximumFractionDigits: d});
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

const ICON = {
  prompts: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%;height:100%"><polyline points="4 7 9 12 4 17"></polyline><line x1="12" y1="17" x2="20" y2="17"></line></svg>',
  links: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%;height:100%"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"></path><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"></path></svg>',
  settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%;height:100%"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>',
  down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%;height:100%"><polyline points="6 9 12 15 18 9"></polyline></svg>',
  up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%;height:100%"><polyline points="18 15 12 9 6 15"></polyline></svg>',
};

/* ---------------- persisted state ---------------- */
const store = {
  get(k, d) { try { const v = localStorage.getItem('hlbt.' + k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem('hlbt.' + k, v); } catch {} },
};
const S = {
  filter: '',
  winnersOnly: store.get('winnersOnly', '0') === '1',
  sortKey: store.get('sortKey', 'return_pct'),
  sortDir: Number(store.get('sortDir', -1)),
  tab: store.get('tab', 'prompts'),
  open: store.get('panelOpen', '1') === '1',
  sparklines: store.get('sparklines', '1') === '1',
  highlight: store.get('highlight', '1') === '1',
};

/* ---------------- table ---------------- */
const COLS = [
  {label: 'STRATEGY', key: 'strategy', align: 'l'},
  {label: 'PERPS', key: 'symbol', align: 'l'},
  {label: 'TIMEFRAME', key: 'timeframe', align: 'l', noSort: true},
  {label: 'TRADES', key: 'trades', align: 'r'},
  {label: 'WIN RATE', key: 'win_rate', align: 'r'},
  {label: 'PROFIT FACTOR', key: 'profit_factor', align: 'r'},
  {label: 'R:R', key: 'risk_reward', align: 'r'},
  {label: 'EXPECTANCY', key: 'expectancy', align: 'r'},
  {label: 'RETURN', key: 'return_pct', align: 'r'},
  {label: 'MAX DRAWDOWN', key: 'max_dd', align: 'r'},
  {label: 'SHARPE', key: 'sharpe', align: 'r'},
  {label: 'FEES', key: 'fees', align: 'r'},
];

function spark(curve, positive) {
  if (!S.sparklines || !curve || curve.length < 2) return '';
  const w = 94, h = 30, pad = 3;
  const min = Math.min(...curve, 0), max = Math.max(...curve, 0);
  const range = (max - min) || 1;
  const x = i => (i / (curve.length - 1)) * w;
  const y = v => h - pad - ((v - min) / range) * (h - pad * 2);
  let path = '';
  curve.forEach((v, i) => { path += (i === 0 ? 'M' : 'L') + x(i).toFixed(2) + ' ' + y(v).toFixed(2) + ' '; });
  const zero = y(0).toFixed(2);
  const area = path + 'L' + w + ' ' + zero + ' L0 ' + zero + ' Z';
  const col = positive ? 'var(--accent)' : '#f04b5c';
  const fill = positive ? 'rgba(52,211,153,.12)' : 'rgba(240,75,92,.12)';
  return '<svg width="94" height="30" viewBox="0 0 94 30" preserveAspectRatio="none" style="display:inline-block;vertical-align:middle">'
    + '<line x1="0" y1="' + zero + '" x2="94" y2="' + zero + '" stroke="rgba(120,140,135,.25)" stroke-width="0.75" stroke-dasharray="2 2"></line>'
    + '<path d="' + area + '" fill="' + fill + '"></path>'
    + '<path d="' + path.trim() + '" fill="none" stroke="' + col + '" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"></path>'
    + '</svg>';
}

function visibleRows() {
  let list = ROWS.slice();
  const f = S.filter.trim().toLowerCase();
  if (f) list = list.filter(r => r.strategy.toLowerCase().includes(f) || String(r.symbol).toLowerCase().includes(f));
  if (S.winnersOnly) list = list.filter(r => r.return_pct > 0);
  const k = S.sortKey;
  list.sort((a, b) => {
    const av = a[k], bv = b[k];
    const cmp = typeof av === 'string' ? av.localeCompare(bv) : (av - bv);
    return cmp * S.sortDir;
  });
  return list;
}

function renderTable() {
  const list = visibleRows();
  const head = COLS.map(c => {
    const on = S.sortKey === c.key;
    const ind = on ? (S.sortDir === 1 ? '▲' : '▼') : '';
    return '<th class="' + c.align + (c.noSort ? '' : ' sortable') + (on ? ' on' : '') + '"'
      + (c.noSort ? '' : ' data-sort="' + c.key + '"') + '>'
      + '<span style="display:inline-flex;align-items:center;gap:5px">' + c.label
      + '<span class="ind">' + ind + '</span></span></th>';
  }).join('') + '<th class="c">EQUITY</th><th></th>';

  const body = list.map(r => {
    const win = S.highlight && r.return_pct > 0;
    const exp = (r.expectancy >= 0 ? '+$' : '−$') + fmt(Math.abs(r.expectancy));
    const replay = r.href
      ? '<a class="replay" href="' + esc(r.href) + '">▶ Replay</a>'
      : '<span class="dim" style="font-size:10px">run hlbt demo</span>';
    return '<tr class="' + (win ? 'win' : '') + '">'
      + '<td class="l"><span class="strat">' + esc(r.strategy) + '</span></td>'
      + '<td class="l"><span class="chip">' + esc(r.symbol) + '</span></td>'
      + '<td class="l dim">' + esc(r.timeframe) + '</td>'
      + '<td class="r">' + r.trades + '</td>'
      + '<td class="r">' + fmt(r.win_rate, 1) + '%</td>'
      + '<td class="r">' + fmt(r.profit_factor) + '</td>'
      + '<td class="r">' + fmt(r.risk_reward) + '</td>'
      + '<td class="r ' + (r.expectancy >= 0 ? 'pos' : 'neg') + '">' + exp + '</td>'
      + '<td class="r ' + (r.return_pct >= 0 ? 'pos' : 'neg') + '">' + (r.return_pct >= 0 ? '+' : '') + fmt(r.return_pct) + '%</td>'
      + '<td class="r neg">' + fmt(r.max_dd) + '%</td>'
      + '<td class="r" style="color:' + (r.sharpe >= 0 ? '#c9d4d1' : '#f04b5c') + '">' + fmt(r.sharpe) + '</td>'
      + '<td class="r dim">$' + fmt(r.fees) + '</td>'
      + '<td class="c">' + spark(r.spark, r.return_pct >= 0) + '</td>'
      + '<td class="r">' + replay + '</td></tr>';
  }).join('');

  $('table').innerHTML = '<thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody>';
  $('empty').hidden = list.length > 0;
  $('empty').textContent = S.filter
    ? 'No runs match “' + S.filter + '”.'
    : 'No runs yet — run hlbt demo on a result.';
  $('shown').textContent = list.length + ' of ' + ROWS.length + ' shown';

  $('table').querySelectorAll('th[data-sort]').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.sort;
      if (S.sortKey === k) S.sortDir = -S.sortDir;
      else { S.sortKey = k; S.sortDir = (k === 'strategy' || k === 'symbol') ? 1 : -1; }
      store.set('sortKey', S.sortKey); store.set('sortDir', S.sortDir);
      renderTable();
    };
  });
}

/* ---------------- panel content ---------------- */
const PROMPT_CREATE = [
"I want to create a new crypto trading strategy for the Hyperliquid Backtester",
"(github.com/Crypto-Data-API/hyperliquid-backtester), which is checked out here.",
"",
"First, ask me what kind of strategy I want. If I don't have one in mind, propose",
"three distinct ideas from DIFFERENT edge families — mean reversion, trend, carry,",
"liquidation, breakout, market-making — and let me pick. For each, state the",
"economic reason the edge should exist in one sentence. If the AlgoBrain MCP server",
"is connected (github.com/Crypto-Data-API/algobrain), search it first for the",
"relevant family and base the idea on what you find.",
"",
"Then read docs/WRITING-STRATEGIES.md and write it to strategies/user/NAME.py:",
"  - a Strategy subclass returning a Signal from on_bar()",
"  - an exit reason from should_exit()",
"  - tunable class attributes, not hardcoded numbers",
"  - a docstring naming the economic rationale and the expected failure mode",
"",
"Then run it and show me the result:",
"  hlbt run --strategy strategies/user/NAME.py --symbol BTC --timeframe 15m --json-out results/NAME.json",
"  hlbt demo results/NAME.json",
"",
"Report profit factor, expectancy, max drawdown and fees alongside win rate — and",
"tell me honestly if the trade count is too low to mean anything yet.",
].join("\n");

const PROMPT_DATA = [
"Set up market data for the Hyperliquid Backtester in this repo.",
"",
"1. Add the CryptoDataAPI MCP server. It is keyless — a browser sign-in opens on the",
"   first tool call and creates a free account:",
"",
"     claude mcp add --transport http cryptodataapi https://cryptodataapi.com/mcp",
"",
"2. Use the MCP tools to tell me which Hyperliquid symbols have the deepest history",
"   right now, and what date range each covers.",
"",
"3. Then sync the data locally. Bulk history needs a Pro Plus key set as",
"   CRYPTODATA_API_KEY — tell me if mine is missing or too low a tier:",
"",
"     hlbt sync --symbol BTC ETH SOL --timeframe 15m --days 90",
"",
"4. Report the bar count and date range written for each symbol. Flag any symbol",
"   that came back with a SHORTER window than I asked for — the query endpoints",
"   clamp silently to the earliest available bar rather than erroring.",
"",
"Then read docs/DATA-SYNC.md and tell me whether the deep Parquet tiers would give",
"me a longer window for the timeframe I want.",
].join("\n");

const PROMPT_LIVE = [
"I have a backtested strategy in this repo and I am considering trading it live.",
"Be blunt with me rather than encouraging.",
"",
"1. Read docs/VALIDATION.md, then look at my run in results/ and tell me:",
"   - is the trade count large enough to mean anything?",
"   - how many variants did I try before this one, and does that change the result?",
"   - do fees and funding eat most of the gross profit?",
"",
"2. Explain what this backtest does NOT model — order-book depth, partial fills,",
"   market impact — and how each would change my fills at the size I intend to trade.",
"   Re-run with a much higher --slippage and show me whether the edge survives.",
"",
"3. Then walk me through going live safely: paper trading first, what to compare",
"   against the backtest, position sizing, and a portfolio-level kill switch.",
"",
"Exchange sign-up with fee discounts:",
"  Hyperliquid (4% off spot & perp fees):",
"    https://app.hyperliquid.xyz/join/CRYPTODATAAPI",
"  Binance (10% off trading fees):",
"    https://www.binance.com/register?ref=RZSKG1XM",
"",
"Live market data for the agent: https://cryptodataapi.com/mcp",
"",
"Do not tell me whether to take a trade. I want the mechanics and the risks.",
].join("\n");

const PROMPTS = [
  {id: 'create', accent: '#34d399', title: 'CREATE A NEW STRATEGY',
   desc: 'The agent asks what you want to build — or proposes ideas from different edge families if you have none in mind.',
   link: {href: 'https://github.com/Crypto-Data-API/algobrain', label: 'AlgoBrain'},
   body: PROMPT_CREATE},
  {id: 'data', accent: '#4a9eff', title: 'DOWNLOAD BACKTEST DATA',
   desc: 'Connect the CryptoDataAPI MCP server, then sync Hyperliquid klines and funding into this backtester.',
   link: {href: 'https://cryptodataapi.com/pricing?code=SOCIAL50', label: 'Get a key'},
   body: PROMPT_DATA},
  {id: 'live', accent: '#f5a623', title: 'TRADE LIVE ON AN EXCHANGE',
   desc: 'Before risking capital: what the backtest does not model, and how to check the strategy survives contact with real fills.',
   link: {href: 'https://app.hyperliquid.xyz/join/CRYPTODATAAPI', label: 'Hyperliquid'},
   body: PROMPT_LIVE},
];

const REPO = 'https://github.com/Crypto-Data-API/hyperliquid-backtester';
const LINK_GROUPS = [
  {title: 'EXCHANGES', items: [
    {name: 'Hyperliquid', tag: '4% off fees · referral', href: 'https://app.hyperliquid.xyz/join/CRYPTODATAAPI'},
    {name: 'Binance', tag: '10% off fees · referral', href: 'https://www.binance.com/register?ref=RZSKG1XM'},
  ]},
  {title: 'DATA & IDEAS', items: [
    {name: 'Get an API key', tag: '50% off 3 months', href: 'https://cryptodataapi.com/pricing?code=SOCIAL50'},
    {name: 'Backtest data', tag: 'coverage & docs', href: 'https://cryptodataapi.com/backtest-data'},
    {name: 'AlgoBrain', tag: 'strategy ideas · free', href: 'https://github.com/Crypto-Data-API/algobrain'},
    {name: 'MCP server', tag: 'setup guide', href: 'https://cryptodataapi.com/ai-agents/mcp-server'},
  ]},
  {title: 'PROJECT', items: [
    {name: 'hyperliquid-backtester', tag: 'github · MIT', href: REPO},
    {name: 'WRITING-STRATEGIES.md', tag: 'docs', href: REPO + '/blob/main/docs/WRITING-STRATEGIES.md'},
    {name: 'DATA-SYNC.md', tag: 'docs', href: REPO + '/blob/main/docs/DATA-SYNC.md'},
    {name: 'VALIDATION.md', tag: 'docs', href: REPO + '/blob/main/docs/VALIDATION.md'},
  ]},
];

const SETTINGS = [
  {key: 'sparklines', label: 'Show equity sparklines', desc: 'Mini P&L curve per run in the table.'},
  {key: 'highlight', label: 'Highlight profitable runs', desc: 'Accent bar + tint on positive-return rows.'},
  {key: 'winnersOnly', label: 'Profitable only', desc: 'Hide runs with a negative return.'},
];

const SUBS = {
  prompts: 'Copy a prompt into Claude Code, Cursor, or any AI agent with a terminal.',
  links: 'Exchange, data and project links. Referral links may carry a discount for you.',
  settings: 'Table & display preferences. Saved in this browser.',
};

function renderPane() {
  const host = $('paneContent');
  $('paneTitle').textContent = S.tab.toUpperCase();
  $('paneSub').textContent = SUBS[S.tab];
  $('paneIcon').innerHTML = ICON[S.tab];

  if (S.tab === 'prompts') {
    host.innerHTML = '<div class="grid p">' + PROMPTS.map(p =>
      '<div class="card" style="--c:' + p.accent + '">'
      + '<div class="h"><div class="t">' + p.title + '</div><div class="d">' + esc(p.desc) + '</div></div>'
      + '<pre class="hb-scroll" id="pre-' + p.id + '">' + esc(p.body) + '</pre>'
      + '<div class="f"><button class="copy" data-copy="' + p.id + '">Copy prompt</button>'
      + '<a href="' + p.link.href + '" target="_blank" rel="noopener" style="font-size:11px;color:#7d908b">'
      + p.link.label + ' ↗</a></div></div>').join('') + '</div>';
    host.querySelectorAll('[data-copy]').forEach(btn => btn.onclick = () => copyPrompt(btn));
  } else if (S.tab === 'links') {
    host.innerHTML = '<div class="grid l">' + LINK_GROUPS.map(g =>
      '<div class="lgroup"><div class="gt">' + g.title + '</div>' + g.items.map(l =>
        '<a href="' + l.href + '" target="_blank" rel="noopener"><span class="n">' + esc(l.name)
        + '</span><span class="tg">' + esc(l.tag) + ' ↗</span></a>').join('')
      + '</div>').join('') + '</div>';
  } else {
    host.innerHTML = '<div class="grid l"><div class="lgroup" style="padding:6px 16px">'
      + SETTINGS.map(s =>
        '<div class="setrow"><div><div class="lb">' + s.label + '</div><div class="ds">' + esc(s.desc)
        + '</div></div><button class="sw" data-set="' + s.key + '" aria-pressed="' + S[s.key] + '"><i></i></button></div>').join('')
      + '</div><div class="disc"><div class="gt">DISCLAIMER</div>'
      + 'Data provided by <a href="https://cryptodataapi.com/backtest-data" target="_blank" rel="noopener">CryptoDataAPI</a>'
      + ' · strategy ideas provided by <a href="https://github.com/Crypto-Data-API/algobrain" target="_blank" rel="noopener">AlgoBrain</a>'
      + ' · exchange links may contain referrals (at no cost to you — to claim your trading discounts on sign-up)'
      + ' · historical simulations from real data, not predictions · nothing here is financial advice'
      + ' · <strong>overfitting is real</strong> — backtesting trading is not the same as real market trading.'
      + '</div></div>';
    host.querySelectorAll('[data-set]').forEach(btn => btn.onclick = () => {
      const k = btn.dataset.set;
      S[k] = !S[k];
      store.set(k, S[k] ? '1' : '0');
      btn.setAttribute('aria-pressed', String(S[k]));
      if (k === 'winnersOnly') $('winnersOnly').setAttribute('aria-pressed', String(S[k]));
      renderTable();
    });
  }
}

function copyPrompt(btn) {
  const node = $('pre-' + btn.dataset.copy);
  const text = node.textContent;
  const done = ok => {
    btn.textContent = ok ? '✓ Copied' : 'Selected — press Ctrl+C';
    btn.classList.add('done');
    setTimeout(() => { btn.textContent = 'Copy prompt'; btn.classList.remove('done'); }, 2000);
  };
  navigator.clipboard.writeText(text).then(() => done(true)).catch(() => {
    const r = document.createRange();
    r.selectNodeContents(node);
    const sel = window.getSelection();
    sel.removeAllRanges(); sel.addRange(r);
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e) {}
    done(ok);
  });
}

/* ---------------- panel chrome ---------------- */
function setPanel(open, persist) {
  S.open = open;
  $('panebody').hidden = !open;
  $('collapse').innerHTML = open ? ICON.down : ICON.up;
  $('collapse').title = open ? 'Collapse panel' : 'Expand panel';
  if (persist) store.set('panelOpen', open ? '1' : '0');
}

document.querySelectorAll('.rail [data-pane]').forEach(btn => {
  btn.innerHTML = ICON[btn.dataset.pane];
  btn.onclick = () => {
    if (S.open && S.tab === btn.dataset.pane) { setPanel(false, true); return; }
    S.tab = btn.dataset.pane;
    store.set('tab', S.tab);
    document.querySelectorAll('.rail [data-pane]').forEach(b =>
      b.setAttribute('aria-selected', String(b.dataset.pane === S.tab)));
    renderPane();
    setPanel(true, true);
  };
});
$('collapse').onclick = () => setPanel(!S.open, true);

$('filter').oninput = e => { S.filter = e.target.value; renderTable(); };
$('winnersOnly').onclick = () => {
  S.winnersOnly = !S.winnersOnly;
  store.set('winnersOnly', S.winnersOnly ? '1' : '0');
  $('winnersOnly').setAttribute('aria-pressed', String(S.winnersOnly));
  renderTable();
  if (S.tab === 'settings') renderPane();
};

/* ---------------- boot ---------------- */
const profitable = ROWS.filter(r => r.return_pct > 0).length;
$('runCount').textContent = ROWS.length + (ROWS.length === 1 ? ' run' : ' runs');
$('profitable').textContent = profitable + ' / ' + ROWS.length + ' profitable';
$('winnersOnly').setAttribute('aria-pressed', String(S.winnersOnly));
document.querySelectorAll('.rail [data-pane]').forEach(b =>
  b.setAttribute('aria-selected', String(b.dataset.pane === S.tab)));
renderTable();
renderPane();
setPanel(S.open, false);
</script>
</body>
</html>
"""

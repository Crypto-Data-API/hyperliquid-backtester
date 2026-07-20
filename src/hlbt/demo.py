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
        rows.append({
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
      <option value="1">1×</option>
      <option value="4" selected>4×</option>
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
<style>
  :root{
    --bg:#070b0a; --panel:#0d1412; --line:#1b2b26; --text:#e6f2ee;
    --dim:#7d968e; --green:#34e29b; --red:#ef4b6b; --accent:#34e29b;
  }
  *{box-sizing:border-box}
  /* The index scrolls, so min-height rather than height — and 100vh rather
     than 100%, which would resolve against an auto-height html and collapse,
     leaving the launcher floating mid-page instead of pinned to the bottom. */
  body{min-height:100vh;margin:0;background:var(--bg);color:var(--text);
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
  main{flex:1 1 auto;padding:20px 18px;width:100%;
    display:flex;flex-direction:column}
  /* the launcher sits at the bottom of the page: the run list absorbs the
     slack when there are few runs, and everything flows normally when there
     are many */
  #body{flex:0 0 auto}
  .next{margin-top:auto;padding-top:26px}
  h1{font-size:19px;margin:0 0 4px}
  .sub{color:var(--dim);font-size:13px;margin-bottom:18px}
  table{width:100%;border-collapse:collapse;background:var(--panel);
    border:1px solid var(--line);border-radius:12px;overflow:hidden}
  th,td{text-align:right;padding:11px 14px;border-bottom:1px solid var(--line);
    font:13px/1.4 ui-monospace,monospace;white-space:nowrap}
  th{font:600 10.5px/1.4 ui-sans-serif,system-ui;color:var(--dim);
    text-transform:uppercase;letter-spacing:.06em;background:#0a120f}
  /* strategy, perps and timeframe read as labels, so left-align them;
     every numeric column stays right-aligned for column-wise comparison */
  th:first-child,td:first-child,
  th:nth-child(2),td:nth-child(2),
  th:nth-child(3),td:nth-child(3){text-align:left}
  tbody tr:last-child td{border-bottom:0}
  tbody tr:hover{background:rgba(52,226,155,.05)}
  td a{color:var(--text);text-decoration:none;font-weight:700}
  td a:hover{color:var(--accent)}
  .up{color:var(--green)} .down{color:var(--red)} .muted{color:var(--dim)}
  .play{display:inline-block;background:var(--accent);color:#04120c;
    border-radius:7px;padding:5px 13px;font:700 11.5px/1 ui-sans-serif,system-ui;
    text-decoration:none}
  .play:hover{filter:brightness(1.08)}
  .none{color:var(--dim);font-size:11.5px}
  .empty{padding:36px;text-align:center;color:var(--dim);background:var(--panel);
    border:1px solid var(--line);border-radius:12px}
  code{background:#0a1310;border:1px solid var(--line);border-radius:5px;
    padding:2px 7px;font-size:12px;color:var(--text)}
  .wrap{overflow-x:auto}
  /* --- next-step launcher cards ------------------------------------- */
  h2.section{font-size:15px;margin:30px 0 4px}
  /* --- collapsible panel -------------------------------------------- */
  .panel{border:1px solid var(--line);border-radius:12px;background:#0a120f;
    overflow:hidden}
  .panelbar{display:flex;align-items:center;gap:11px;flex-wrap:wrap;
    padding:5px 13px;min-height:0}
  .tabs{display:flex;gap:2px}
  .tab{background:transparent;border:0;cursor:pointer;color:var(--dim);
    font:700 11px/1 ui-sans-serif,system-ui;letter-spacing:.09em;
    text-transform:uppercase;padding:9px 12px;border-radius:0;
    border-bottom:2px solid transparent;transition:color .12s}
  .tab:hover{color:var(--text)}
  .tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
  .panelsub{flex:1;min-width:180px;font-size:11.5px;color:var(--dim);
    line-height:1.3}
  .pane[hidden]{display:none}
  .mini{background:transparent;color:var(--dim);border:1px solid var(--line);
    border-radius:6px;padding:4px 11px;font:600 11px/1.3 inherit;cursor:pointer;
    white-space:nowrap}
  .mini:hover{color:var(--accent);border-color:var(--accent)}
  .mini::before{content:"▾ ";font-size:9px}
  .panel.collapsed .mini::before{content:"▸ "}
  .panelbody{padding:2px 13px 14px;border-top:1px solid var(--line)}
  .panelbody[hidden]{display:none}
  .panelbody .cards{margin-top:12px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));
    gap:14px;margin-top:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    display:flex;flex-direction:column;overflow:hidden}
  .card header{border-top:3px solid var(--c);background:linear-gradient(
      to bottom, color-mix(in srgb, var(--c) 12%, transparent), transparent);
    padding:12px 15px 11px}
  .card h3{margin:0;font-size:13px;letter-spacing:.05em;text-transform:uppercase;
    color:var(--c)}
  .card .why{margin:5px 0 0;font-size:12px;color:var(--dim);line-height:1.55}
  .card pre{flex:1;margin:0;padding:13px 15px;overflow:auto;max-height:290px;
    font:11.5px/1.65 ui-monospace,monospace;color:var(--text);white-space:pre-wrap;
    word-break:break-word;border-top:1px solid var(--line)}
  .card .foot{display:flex;align-items:center;gap:10px;padding:11px 15px;
    border-top:1px solid var(--line);background:#0a120f}
  .copy{background:var(--c);color:#04120c;border:0;border-radius:7px;
    padding:8px 16px;font:700 12px/1 inherit;cursor:pointer}
  .copy:hover{filter:brightness(1.08)}
  .copy.done{background:transparent;color:var(--c);
    box-shadow:inset 0 0 0 1px var(--c)}
  /* --- useful links ------------------------------------------------- */
  /* Quiet by design. The copy buttons above are the primary action, so these
     stay as text links — six filled buttons made the secondary thing louder
     than the primary one. */
  .linkrow{display:flex;flex-wrap:wrap;gap:6px 26px;margin-top:10px}
  .btn{display:inline-flex;align-items:baseline;gap:7px;text-decoration:none;
    color:var(--text);font-size:12.5px}
  .btn b{font-weight:600;border-bottom:1px solid var(--line);
    padding-bottom:1px;transition:color .12s, border-color .12s}
  .btn:hover b{color:var(--accent);border-bottom-color:var(--accent)}
  .btn span{color:var(--dim);font-size:11.5px}
  /* new-window marker, driven off the attribute so it can never drift out of
     sync with which links actually open a tab */
  .btn[target="_blank"]::after{content:"↗";font-size:10.5px;color:var(--dim);
    margin-left:-3px}
  footer{flex:0 0 auto;padding:16px 18px 24px;color:var(--dim);font-size:11.5px;
    line-height:1.7}
  footer a{color:var(--accent)}
</style>
</head>
<body>
<header>
  <a class="brand" href="index.html">
    <span class="mark">▚</span> HYPERLIQUID <span class="hl">BACKTESTER</span>
  </a>
  <div class="tag" id="count">—</div>
</header>

<main>
  <h1>Backtest runs</h1>
  <div class="sub">Every result exported to this folder. Click a run to replay it bar by bar.</div>
  <div id="body"></div>

  <section class="next panel" id="nextPanel">
    <div class="panelbar">
      <nav class="tabs" role="tablist" aria-label="What next">
        <button class="tab" role="tab" data-pane="prompts"
                aria-controls="pane-prompts" aria-selected="true">Prompts</button>
        <button class="tab" role="tab" data-pane="links"
                aria-controls="pane-links" aria-selected="false">Links</button>
      </nav>
      <span class="panelsub" id="paneHint"></span>
      <button class="mini" id="nextToggle" aria-controls="nextBody"
              aria-expanded="true">Minimise</button>
    </div>
    <div class="panelbody" id="nextBody">

    <div class="pane" id="pane-prompts" role="tabpanel">
  <div class="cards">

    <div class="card" style="--c:#34e29b">
      <header>
        <h3>Create a new strategy</h3>
        <p class="why">The agent asks what you want to build — or proposes ideas from
          different edge families if you have none in mind.</p>
      </header>
<pre id="p1">I want to create a new crypto trading strategy for the Hyperliquid Backtester
(github.com/Crypto-Data-API/hyperliquid-backtester), which is checked out here.

First, ask me what kind of strategy I want. If I don't have one in mind, propose
three distinct ideas from DIFFERENT edge families — mean reversion, trend, carry,
liquidation, breakout, market-making — and let me pick. For each, state the
economic reason the edge should exist in one sentence. If the AlgoBrain MCP server
is connected (github.com/Crypto-Data-API/algobrain), search it first for the
relevant family and base the idea on what you find.

Then read docs/WRITING-STRATEGIES.md and write it to strategies/user/NAME.py:
  - a Strategy subclass returning a Signal from on_bar()
  - an exit reason from should_exit()
  - tunable class attributes, not hardcoded numbers
  - a docstring naming the economic rationale and the expected failure mode

Then run it and show me the result:
  hlbt run --strategy strategies/user/NAME.py --symbol BTC --timeframe 15m --json-out results/NAME.json
  hlbt demo results/NAME.json

Report profit factor, expectancy, max drawdown and fees alongside win rate — and
tell me honestly if the trade count is too low to mean anything yet.</pre>
      <div class="foot">
        <button class="copy" data-target="p1">Copy prompt</button>
      </div>
    </div>

    <div class="card" style="--c:#4db8ff">
      <header>
        <h3>Download backtest data</h3>
        <p class="why">Connect the CryptoDataAPI MCP server, then sync Hyperliquid
          klines and funding into this backtester.</p>
      </header>
<pre id="p2">Set up market data for the Hyperliquid Backtester in this repo.

1. Add the CryptoDataAPI MCP server. It is keyless — a browser sign-in opens on the
   first tool call and creates a free account:

     claude mcp add --transport http cryptodataapi https://cryptodataapi.com/mcp

2. Use the MCP tools to tell me which Hyperliquid symbols have the deepest history
   right now, and what date range each covers.

3. Then sync the data locally. Bulk history needs a Pro Plus key set as
   CRYPTODATA_API_KEY — tell me if mine is missing or too low a tier:

     hlbt sync --symbol BTC ETH SOL --timeframe 15m --days 90

4. Report the bar count and date range written for each symbol. Flag any symbol
   that came back with a SHORTER window than I asked for — the query endpoints
   clamp silently to the earliest available bar rather than erroring.

Then read docs/DATA-SYNC.md and tell me whether the deep Parquet tiers would give
me a longer window for the timeframe I want.</pre>
      <div class="foot">
        <button class="copy" data-target="p2">Copy prompt</button>
      </div>
    </div>

    <div class="card" style="--c:#f5a524">
      <header>
        <h3>Trade live on an exchange</h3>
        <p class="why">Before risking capital: what the backtest does not model, and
          how to check the strategy survives contact with real fills.</p>
      </header>
<pre id="p3">I have a backtested strategy in this repo and I am considering trading it live.
Be blunt with me rather than encouraging.

1. Read docs/VALIDATION.md, then look at my run in results/ and tell me:
   - is the trade count large enough to mean anything?
   - how many variants did I try before this one, and does that change the result?
   - do fees and funding eat most of the gross profit?

2. Explain what this backtest does NOT model — order-book depth, partial fills,
   market impact — and how each would change my fills at the size I intend to trade.
   Re-run with a much higher --slippage and show me whether the edge survives.

3. Then walk me through going live safely: paper trading first, what to compare
   against the backtest, position sizing, and a portfolio-level kill switch.

Exchange sign-up with fee discounts:
  Hyperliquid (4% off spot & perp fees):
    https://app.hyperliquid.xyz/join/CRYPTODATAAPI
  Binance (10% off trading fees):
    https://www.binance.com/register?ref=RZSKG1XM

Live market data for the agent: https://cryptodataapi.com/mcp

Do not tell me whether to take a trade. I want the mechanics and the risks.</pre>
      <div class="foot">
        <button class="copy" data-target="p3">Copy prompt</button>
      </div>
    </div>

  </div>
    </div>

    <div class="pane" id="pane-links" role="tabpanel" hidden>
  <div class="linkrow">
    <a class="btn" target="_blank" rel="noopener"
       href="https://github.com/Crypto-Data-API/algobrain">
      <b>AlgoBrain</b> <span>strategy ideas · free</span></a>
    <a class="btn" target="_blank" rel="noopener"
       href="https://cryptodataapi.com/pricing?code=SOCIAL50">
      <b>Get an API key</b> <span>50% off 3 months</span></a>
    <a class="btn" target="_blank" rel="noopener"
       href="https://cryptodataapi.com/backtest-data">
      <b>Backtest data</b> <span>coverage &amp; docs</span></a>
    <a class="btn" target="_blank" rel="noopener"
       href="https://app.hyperliquid.xyz/join/CRYPTODATAAPI">
      <b>Hyperliquid</b> <span>4% off fees · referral</span></a>
    <a class="btn" target="_blank" rel="noopener"
       href="https://www.binance.com/register?ref=RZSKG1XM">
      <b>Binance</b> <span>10% off fees · referral</span></a>
    <a class="btn" target="_blank" rel="noopener"
       href="https://github.com/Crypto-Data-API/hyperliquid-backtester">
      <b>Source</b> <span>GitHub · MIT</span></a>
  </div>
    </div>

    </div>
  </section>
</main>

<footer>
  Data provided by <a href="https://cryptodataapi.com/backtest-data">CryptoDataAPI</a>
  · strategy ideas provided by
  <a href="https://github.com/Crypto-Data-API/algobrain">AlgoBrain</a>
  · exchange links may contain referrals (at no cost to you — to claim your trading
  discounts on sign-up) · historical simulations from real data, not predictions
  · nothing here is financial advice · <strong>overfitting is real</strong> —
  backtesting trading is not the same as real market trading.
</footer>

<script>
const ROWS = __ROWS__;
const fmt = (n, d = 2) => Number(n).toLocaleString(undefined,
  {minimumFractionDigits: d, maximumFractionDigits: d});
const cls = n => Number(n) >= 0 ? 'up' : 'down';

document.getElementById('count').textContent =
  ROWS.length ? `${ROWS.length} run${ROWS.length > 1 ? 's' : ''}` : '';

const host = document.getElementById('body');

if (!ROWS.length) {
  host.innerHTML = `<div class="empty">
    <p>No runs here yet.</p>
    <p><code>hlbt run --strategy strategies/examples/bollinger_revert.py --symbol BTC --json-out results/btc.json</code></p>
    <p><code>hlbt demo results/btc.json</code></p>
  </div>`;
} else {
  // best return first, so the list is useful the moment it has more than a few rows
  ROWS.sort((a, b) => b.return_pct - a.return_pct);
  host.innerHTML = `<div class="wrap"><table>
    <thead><tr>
      <th>Strategy</th><th>Perps</th><th>Timeframe</th><th>Trades</th>
      <th>Win rate</th><th>Profit factor</th><th title="Average win divided by average loss">R:R</th>
      <th title="Average net profit or loss per trade">Expectancy $</th>
      <th>Return</th><th>Max drawdown</th><th>Sharpe</th><th>Fees</th><th></th>
    </tr></thead>
    <tbody>${ROWS.map(r => `
      <tr>
        <td>${r.href ? `<a href="${r.href}">${r.strategy}</a>` : `<span class="muted">${r.strategy}</span>`}</td>
        <td>${r.symbol}</td>
        <td class="muted">${r.timeframe}</td>
        <td>${r.trades}</td>
        <td>${fmt(r.win_rate, 1)}%</td>
        <td>${fmt(r.profit_factor)}</td>
        <td>${fmt(r.risk_reward)}</td>
        <td class="${cls(r.expectancy)}">${r.expectancy >= 0 ? '+' : '−'}$${fmt(Math.abs(r.expectancy))}</td>
        <td class="${cls(r.return_pct)}">${r.return_pct >= 0 ? '+' : ''}${fmt(r.return_pct)}%</td>
        <td class="down">${fmt(r.max_dd)}%</td>
        <td>${fmt(r.sharpe)}</td>
        <td class="muted">$${fmt(r.fees)}</td>
        <td>${r.href ? `<a class="play" href="${r.href}">▶ Replay</a>`
                     : `<span class="none">run <code>hlbt demo</code></span>`}</td>
      </tr>`).join('')}
    </tbody></table></div>`;
}

// Collapsible "What next" panel. State persists per browser — localStorage is
// wrapped because it throws in Safari private mode and under some file://
// origins, and a storage failure must not cost you the toggle itself.
(() => {
  const COLLAPSE_KEY = 'hlbt.next.collapsed';
  const TAB_KEY = 'hlbt.next.tab';
  const HINTS = {
    prompts: 'Copy a prompt into Claude Code, Cursor, or any AI agent with a terminal.',
    links: 'Market data, strategy ideas, and exchange sign-up.',
  };
  const panel = document.getElementById('nextPanel');
  const body = document.getElementById('nextBody');
  const btn = document.getElementById('nextToggle');
  const hint = document.getElementById('paneHint');
  const tabs = [...document.querySelectorAll('.tab')];
  if (!panel || !body || !btn) return;

  const store = {
    get(k, fallback) { try { return localStorage.getItem(k) ?? fallback; } catch { return fallback; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  };

  function showTab(name, persist) {
    if (!HINTS[name]) name = 'prompts';
    tabs.forEach(t => t.setAttribute('aria-selected', String(t.dataset.pane === name)));
    for (const key of Object.keys(HINTS)) {
      const pane = document.getElementById('pane-' + key);
      if (pane) pane.hidden = key !== name;
    }
    hint.textContent = HINTS[name];
    if (persist) store.set(TAB_KEY, name);
  }

  function setCollapsed(collapsed, persist) {
    body.hidden = collapsed;
    panel.classList.toggle('collapsed', collapsed);
    btn.textContent = collapsed ? 'Show' : 'Minimise';
    btn.setAttribute('aria-expanded', String(!collapsed));
    if (persist) store.set(COLLAPSE_KEY, collapsed ? '1' : '0');
  }

  tabs.forEach(t => t.addEventListener('click', () => {
    showTab(t.dataset.pane, true);
    if (body.hidden) setCollapsed(false, true);   // a tab click means "show me"
  }));
  btn.addEventListener('click', () => setCollapsed(!body.hidden, true));

  showTab(store.get(TAB_KEY, 'prompts'), false);
  setCollapsed(store.get(COLLAPSE_KEY, '0') === '1', false);
})();

// Copy buttons, three ways down. The async clipboard API needs a focused
// document and a secure context, so file:// and unfocused windows fall back to
// execCommand — and if that fails too, the prompt is selected so Ctrl+C works
// rather than leaving the user with a button that did nothing.
document.querySelectorAll('.copy').forEach(btn => {
  const label = btn.textContent;
  btn.addEventListener('click', async () => {
    const node = document.getElementById(btn.dataset.target);
    const text = node.textContent;
    let ok = false;

    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch { /* fall through */ }

    if (!ok) {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      try { ok = document.execCommand('copy'); } catch { ok = false; }
      ta.remove();
    }

    if (!ok) {
      const range = document.createRange();
      range.selectNodeContents(node);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }

    btn.textContent = ok ? '✓ Copied' : 'Selected — press Ctrl+C';
    btn.classList.add('done');
    setTimeout(() => { btn.textContent = label; btn.classList.remove('done'); }, 2200);
  });
});
</script>
</body>
</html>
"""

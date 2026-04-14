"""HTML Dashboard reporter — standalone interactive report.

Generates a single HTML file with embedded CSS and JS. No external
dependencies, works offline. Charts use inline SVG.
"""

from __future__ import annotations

import html
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from decibench.models import EvalResult, SuiteResult


class HTMLReporter:
    """Generate a standalone HTML dashboard for test results."""

    @staticmethod
    def report(result: SuiteResult, output_path: Path | None = None) -> str:
        html_str = _build_html(result)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(html_str, encoding="utf-8")
        return html_str


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

def _score_color(score: float) -> str:
    if score >= 80:
        return "#10b981"
    if score >= 60:
        return "#f59e0b"
    return "#ef4444"


def _score_grade(score: float) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C+"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# SVG constants
# ---------------------------------------------------------------------------

_ARC_R = 120
_ARC_CX, _ARC_CY = 160, 140
_ARC_LEN = math.pi * _ARC_R  # ~376.99

_CATEGORIES = {
    "task_completion": ("Task Completion", 25),
    "latency": ("Latency", 20),
    "audio_quality": ("Audio Quality", 15),
    "conversation": ("Conversation", 15),
    "robustness": ("Robustness", 10),
    "interruption": ("Interruption", 10),
    "compliance": ("Compliance", 5),
}

_RADAR_SHORT = {
    "task_completion": "Task",
    "latency": "Latency",
    "audio_quality": "Audio",
    "conversation": "Conv.",
    "robustness": "Robust.",
    "interruption": "Interrupt.",
    "compliance": "Comply.",
}


# ---------------------------------------------------------------------------
# SVG chart generators
# ---------------------------------------------------------------------------

def _gauge_svg(score: float) -> str:
    """SVG semicircular gauge for the DeciBench score."""
    color = _score_color(score)
    offset = _ARC_LEN * (1 - score / 100)

    angle = math.pi * (1 - score / 100)
    dx = _ARC_CX + _ARC_R * math.cos(angle)
    dy = _ARC_CY - _ARC_R * math.sin(angle)

    dot = ""
    if score > 0:
        dot = (
            f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="7" '
            f'fill="{color}" class="gauge-dot" filter="url(#glow)"/>'
        )

    return f'''<svg viewBox="0 0 320 160" class="gauge-svg">
  <defs>
    <filter id="glow"><feGaussianBlur stdDeviation="3.5" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <path d="M 40 140 A 120 120 0 0 1 280 140" fill="none"
        stroke="#27272a" stroke-width="14" stroke-linecap="round"/>
  <path d="M 40 140 A 120 120 0 0 1 280 140" fill="none"
        stroke="{color}" stroke-width="14" stroke-linecap="round"
        class="gauge-fill" filter="url(#glow)"
        style="stroke-dasharray:{_ARC_LEN:.2f};stroke-dashoffset:{offset:.2f}"/>
  {dot}
  <text x="160" y="105" text-anchor="middle" fill="{color}"
        font-size="48" font-weight="800" font-family="system-ui,sans-serif"
        class="counter" data-target="{score}" data-decimals="1">0</text>
  <text x="160" y="130" text-anchor="middle" fill="#71717a"
        font-size="14" font-family="system-ui,sans-serif">/ 100</text>
</svg>'''


def _radar_svg(categories: dict[str, float]) -> str:
    """SVG radar chart for the 7 quality dimensions."""
    ordered = list(_RADAR_SHORT.keys())
    keys = [k for k in ordered if k in categories]
    n = len(keys)
    if n < 3:
        return '<p class="no-data">Not enough data for radar chart</p>'

    w, h = 340, 340
    cx, cy = 170, 170
    r = 115

    def ang(i: int) -> float:
        return (2 * math.pi * i / n) - math.pi / 2

    def pt(i: int, pct: float) -> tuple[float, float]:
        a = ang(i)
        return cx + r * pct / 100 * math.cos(a), cy + r * pct / 100 * math.sin(a)

    p: list[str] = []

    # Grid rings
    for ring in [20, 40, 60, 80, 100]:
        pts = " ".join(f"{pt(i, ring)[0]:.1f},{pt(i, ring)[1]:.1f}" for i in range(n))
        p.append(f'  <polygon points="{pts}" fill="none" stroke="#27272a"/>')

    # Axes
    for i in range(n):
        x, y = pt(i, 100)
        p.append(f'  <line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#27272a"/>')

    # Data polygon
    vals = [categories.get(k, 50) for k in keys]
    pts = " ".join(f"{pt(i, vals[i])[0]:.1f},{pt(i, vals[i])[1]:.1f}" for i in range(n))
    p.append(
        f'  <polygon points="{pts}" fill="rgba(99,102,241,0.12)"'
        f' stroke="#6366f1" stroke-width="2" stroke-linejoin="round"'
        f' class="radar-poly"/>'
    )

    # Dots
    for i in range(n):
        x, y = pt(i, vals[i])
        p.append(
            f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="4"'
            f' fill="#6366f1" stroke="#18181b" stroke-width="2"/>'
        )

    # Labels
    for i in range(n):
        a = ang(i)
        cos_a = math.cos(a)
        lx = cx + (r + 28) * cos_a
        ly = cy + (r + 28) * math.sin(a)
        anc = "middle" if abs(cos_a) < 0.25 else ("start" if cos_a > 0 else "end")
        name = _RADAR_SHORT.get(keys[i], keys[i])
        val = vals[i]
        vc = _score_color(val)
        p.append(
            f'  <text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anc}"'
            f' dominant-baseline="middle" fill="#a1a1aa" font-size="11"'
            f' font-family="system-ui,sans-serif">{name}</text>'
        )
        p.append(
            f'  <text x="{lx:.1f}" y="{ly + 14:.1f}" text-anchor="{anc}"'
            f' dominant-baseline="middle" fill="{vc}" font-size="12"'
            f' font-weight="700" font-family="system-ui,sans-serif">{val:.0f}</text>'
        )

    return f'<svg viewBox="0 0 {w} {h}" class="radar-svg">\n' + "\n".join(p) + "\n</svg>"


def _latency_svg(results: list[EvalResult]) -> str:
    """SVG horizontal bar chart for per-scenario latency P50."""
    data: list[tuple[str, float]] = []
    for r in results:
        lat = r.metrics.get("turn_latency_p50_ms")
        if lat:
            data.append((r.scenario_id, lat.value))
    if not data:
        return '<p class="no-data">No latency data</p>'

    data.sort(key=lambda x: x[1], reverse=True)
    data = data[:12]
    n = len(data)
    max_v = max(max(v for _, v in data) * 1.15, 1000)

    row_h = 28
    pl, pr, pt, pb = 130, 70, 10, 30
    svg_w = 480
    svg_h = pt + n * row_h + pb
    cw = svg_w - pl - pr
    p: list[str] = []

    # Reference lines
    for ms in [800, 1500]:
        if ms <= max_v:
            x = pl + cw * ms / max_v
            p.append(
                f'  <line x1="{x:.1f}" y1="{pt}" x2="{x:.1f}" y2="{svg_h - pb}"'
                f' stroke="#3f3f46" stroke-dasharray="3,3"/>'
            )
            p.append(
                f'  <text x="{x:.1f}" y="{svg_h - pb + 16}" text-anchor="middle"'
                f' fill="#71717a" font-size="9"'
                f' font-family="system-ui,sans-serif">{ms}ms</text>'
            )

    for i, (name, val) in enumerate(data):
        y = pt + i * row_h + 4
        bw = max(2, cw * val / max_v)
        c = "#10b981" if val < 800 else ("#f59e0b" if val < 1500 else "#ef4444")
        short = (name[:14] + "..") if len(name) > 16 else name
        mid = y + (row_h - 8) / 2 + 1

        p.append(
            f'  <text x="{pl - 8}" y="{mid:.1f}" text-anchor="end"'
            f' dominant-baseline="middle" fill="#a1a1aa" font-size="11"'
            f' font-family="system-ui,sans-serif">{html.escape(short)}</text>'
        )
        p.append(
            f'  <rect x="{pl}" y="{y}" width="{bw:.1f}" height="{row_h - 8}"'
            f' fill="{c}" rx="3" opacity="0.8"/>'
        )
        p.append(
            f'  <text x="{pl + bw + 6:.1f}" y="{mid:.1f}"'
            f' dominant-baseline="middle" fill="#a1a1aa" font-size="10"'
            f' font-family="system-ui,sans-serif">{val:.0f}ms</text>'
        )

    return (
        f'<svg viewBox="0 0 {svg_w} {svg_h}" class="latency-chart">\n'
        + "\n".join(p) + "\n</svg>"
    )


# ---------------------------------------------------------------------------
# HTML fragment generators
# ---------------------------------------------------------------------------

def _stat_cards_html(result: SuiteResult, avg_lat: float) -> str:
    pct = (result.passed / result.total_scenarios * 100) if result.total_scenarios else 0
    pc = _score_color(pct)
    lc = "#10b981" if avg_lat < 800 else ("#f59e0b" if avg_lat < 1500 else "#ef4444")
    ls = f"{avg_lat:.0f}ms" if avg_lat > 0 else "\u2014"
    judge = html.escape(result.judge_model) if result.judge_model else "deterministic"
    return f"""<div class="stat-card">
  <div class="stat-value" style="color:{pc}">{result.passed}/{result.total_scenarios}</div>
  <div class="stat-label">Scenarios Passed</div>
  <div class="stat-bar"><div class="stat-bar-fill" style="width:{pct:.0f}%;background:{pc}"></div></div>
</div>
<div class="stat-card">
  <div class="stat-value" style="color:{lc}">{ls}</div>
  <div class="stat-label">Avg Latency P50</div>
</div>
<div class="stat-card">
  <div class="stat-value stat-value-sm">{judge}</div>
  <div class="stat-label">LLM Judge</div>
</div>
<div class="stat-card">
  <div class="stat-value">{result.duration_seconds:.1f}s</div>
  <div class="stat-label">Total Duration</div>
</div>"""


def _category_bars_html(categories: dict[str, float]) -> str:
    rows = []
    for i, (key, (name, weight)) in enumerate(_CATEGORIES.items()):
        val = categories.get(key, 0)
        c = _score_color(val)
        rows.append(
            f'<div class="cat-row">'
            f'<div class="cat-info"><span class="cat-name">{name}</span>'
            f'<span class="cat-weight">{weight}%</span></div>'
            f'<div class="cat-bar"><div class="cat-fill"'
            f' style="--fw:{val:.0f}%;--fc:{c};--d:{i * 0.08:.2f}s"></div></div>'
            f'<div class="cat-score" style="color:{c}">{val:.1f}</div></div>'
        )
    return "\n".join(rows)


def _scenario_cards_html(results: list[EvalResult]) -> str:
    cards = []
    for r in sorted(results, key=lambda x: x.score):
        c = _score_color(r.score)
        badge = "badge-pass" if r.passed else "badge-fail"
        status = "PASS" if r.passed else "FAIL"

        pills: list[str] = []
        lat = r.metrics.get("turn_latency_p50_ms")
        if lat:
            pills.append(f'<span class="pill">P50: {lat.value:.0f}ms</span>')
        wer = r.metrics.get("wer")
        if wer:
            pills.append(f'<span class="pill">WER: {wer.value:.1f}%</span>')
        mos = r.metrics.get("mos_ovrl")
        if mos:
            pills.append(f'<span class="pill">MOS: {mos.value:.2f}</span>')
        hallu = r.metrics.get("hallucination_rate")
        if hallu and hallu.value > 0:
            pills.append(f'<span class="pill pill-warn">Hallu: {hallu.value:.1f}%</span>')

        tags = "".join(f'<span class="ftag">{html.escape(t)}</span>' for t in r.failure_summary)
        tags_div = f'<div class="sc-fails">{tags}</div>' if tags else ""

        cards.append(
            f'<div class="sc-card">'
            f'<div class="sc-bar" style="width:{max(r.score, 3):.0f}%;background:{c}"></div>'
            f'<div class="sc-body">'
            f'<div class="sc-head"><span class="sc-id">{html.escape(r.scenario_id)}</span>'
            f'<span class="{badge}">{status}</span></div>'
            f'<div class="sc-score" style="color:{c}">{r.score:.1f}</div>'
            f'<div class="sc-pills">{"".join(pills)}</div>'
            f'{tags_div}</div></div>'
        )
    return "\n".join(cards)


def _failed_details_html(results: list[EvalResult]) -> str:
    failed = [r for r in results if not r.passed]
    if not failed:
        return ""

    sections = []
    for r in failed:
        lis = "\n".join(f"<li>{html.escape(f)}</li>" for f in r.failures[:6])
        mrows = []
        for name, m in sorted(r.metrics.items()):
            cls = ' class="mfail"' if not m.passed else ""
            thr = f"{m.threshold}" if m.threshold is not None else "\u2014"
            mrows.append(
                f"<tr{cls}><td>{html.escape(name)}</td><td>{m.value:.2f}</td>"
                f"<td>{html.escape(m.unit)}</td><td>{thr}</td>"
                f"<td>{'PASS' if m.passed else 'FAIL'}</td></tr>"
            )

        sections.append(f"""<details class="fd">
  <summary><span class="badge-fail">FAIL</span>
    <strong>{html.escape(r.scenario_id)}</strong>
    <span class="fd-score">Score: {r.score:.1f}</span></summary>
  <div class="fd-body">
    <h4>Failures</h4><ul>{lis}</ul>
    <h4>All Metrics</h4>
    <table class="fd-tbl">
      <thead><tr><th>Metric</th><th>Value</th><th>Unit</th><th>Threshold</th><th>Status</th></tr></thead>
      <tbody>{"".join(mrows)}</tbody>
    </table>
  </div>
</details>""")

    return f"""
<section class="card fade-in" style="--d:0.25s">
  <div class="card-hdr"><h2>Failed Scenarios</h2>
    <span class="badge-fail">{len(failed)} failed</span></div>
  {"".join(sections)}
</section>"""


def _metric_summary_html(results: list[EvalResult]) -> str:
    sums: dict[str, list[float]] = {}
    units: dict[str, str] = {}
    passes: dict[str, list[bool]] = {}

    for r in results:
        for name, m in r.metrics.items():
            sums.setdefault(name, []).append(m.value)
            units[name] = m.unit
            passes.setdefault(name, []).append(m.passed)

    rows = []
    for name in sorted(sums):
        vals = sums[name]
        avg = sum(vals) / len(vals)
        unit = units.get(name, "")
        ok = all(passes.get(name, []))
        cls = "" if ok else ' class="mfail"'
        rows.append(
            f"<tr{cls}><td>{html.escape(name)}</td>"
            f"<td>{avg:.2f}</td><td>{html.escape(unit)}</td>"
            f"<td>{'PASS' if ok else 'FAIL'}</td><td>{len(vals)}</td></tr>"
        )

    return f"""<table class="tbl">
    <thead><tr><th>Metric</th><th>Avg</th><th>Unit</th><th>Status</th><th>N</th></tr></thead>
    <tbody>{"".join(rows)}</tbody></table>"""


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _aggregate_categories(results: list[EvalResult]) -> dict[str, float]:
    """Fallback: aggregate metric results into category scores."""
    from decibench.evaluators.score import _METRIC_CATEGORIES, DecibenchScorer

    scorer = DecibenchScorer()
    cat_vals: dict[str, list[float]] = {}
    for result in results:
        for metric_name, metric in result.metrics.items():
            cat = _METRIC_CATEGORIES.get(metric_name)
            if cat is None:
                continue
            normalized = scorer._normalize_metric(metric_name, metric)
            cat_vals.setdefault(cat, []).append(normalized)

    return {c: round(sum(v) / len(v), 1) for c, v in cat_vals.items()}


# ---------------------------------------------------------------------------
# Main HTML template builder
# ---------------------------------------------------------------------------

def _build_html(result: SuiteResult) -> str:
    score = result.decibench_score
    cats = result.score_breakdown or _aggregate_categories(result.results)

    lats = [r.metrics["turn_latency_p50_ms"].value for r in result.results
            if "turn_latency_p50_ms" in r.metrics]
    avg_lat = sum(lats) / len(lats) if lats else 0
    grade = _score_grade(score)
    sc = _score_color(score)
    bcls = "badge-pass" if result.passed == result.total_scenarios else "badge-fail"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DeciBench Report \u2014 {html.escape(result.target)}</title>
<style>
{_CSS}
</style>
</head>
<body>

<nav class="topbar">
  <div class="topbar-in">
    <div class="logo">
      <span class="logo-mark">dB</span>
      <span class="logo-txt">DeciBench</span>
      <span class="ver">v{html.escape(result.decibench_version)}</span>
    </div>
    <div class="topbar-r">
      <span class="topbar-meta">{html.escape(result.timestamp)}</span>
    </div>
  </div>
</nav>

<main>

<!-- Hero: Score Gauge + Stats -->
<section class="hero fade-in" style="--d:0s">
  <div class="hero-gauge">
    {_gauge_svg(score)}
    <div class="hero-grade" style="color:{sc}">{grade}</div>
  </div>
  <div class="hero-info">
    <div class="hero-target">
      <span class="hi-label">Target</span>
      <code>{html.escape(result.target)}</code>
    </div>
    <div class="hero-suite">
      <span class="hi-label">Suite</span>
      <code>{html.escape(result.suite)}</code>
      <span class="hi-dim">&middot; {result.total_scenarios} scenarios</span>
    </div>
  </div>
  <div class="hero-stats">
    {_stat_cards_html(result, avg_lat)}
  </div>
</section>

<!-- Score Breakdown -->
<section class="card fade-in" style="--d:0.08s">
  <div class="card-hdr">
    <h2>Score Breakdown</h2>
    <span class="card-sub">7 quality dimensions, weighted by importance</span>
  </div>
  <div class="cat-grid">
    {_category_bars_html(cats)}
  </div>
</section>

<!-- Scenarios -->
<section class="card fade-in" style="--d:0.14s">
  <div class="card-hdr">
    <h2>Scenarios</h2>
    <span class="{bcls}">{result.passed}/{result.total_scenarios} passed</span>
  </div>
  <div class="sc-grid">
    {_scenario_cards_html(result.results)}
  </div>
</section>

<!-- Charts -->
<div class="charts-row fade-in" style="--d:0.2s">
  <section class="card">
    <div class="card-hdr"><h2>Quality Radar</h2></div>
    <div class="chart-c">{_radar_svg(cats)}</div>
  </section>
  <section class="card">
    <div class="card-hdr"><h2>Latency per Scenario (P50)</h2></div>
    <div class="chart-c">{_latency_svg(result.results)}</div>
  </section>
</div>

<!-- Failed Details -->
{_failed_details_html(result.results)}

<!-- Metric Summary -->
<section class="card fade-in" style="--d:0.3s">
  <div class="card-hdr"><h2>All Metrics</h2></div>
  {_metric_summary_html(result.results)}
</section>

</main>

<footer>
  <p>Generated by <strong>DeciBench</strong> v{html.escape(result.decibench_version)}
     \u2014 The open standard for voice agent quality.</p>
  <p class="foot-sub">Target: <code>{html.escape(result.target)}</code>
     &bull; Suite: <code>{html.escape(result.suite)}</code></p>
</footer>

<script>
{_JS}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Embedded CSS
# ---------------------------------------------------------------------------

_CSS = """\
:root {
  --bg: #09090b;
  --card: #18181b;
  --card-h: #1f1f23;
  --bdr: #27272a;
  --bdr2: #3f3f46;
  --tx: #fafafa;
  --tx2: #a1a1aa;
  --tx3: #71717a;
  --accent: #6366f1;
  --green: #10b981;
  --yellow: #f59e0b;
  --red: #ef4444;
  --r: 12px;
}

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--tx);
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}

code {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Mono', Consolas, monospace;
  background: rgba(39,39,42,.5);
  padding: .1rem .45rem;
  border-radius: 5px;
  font-size: .82rem;
}

/* ─── Topbar ─── */
.topbar {
  position: sticky; top: 0; z-index: 50;
  background: rgba(9,9,11,.82);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--bdr);
  padding: .65rem 1.5rem;
}
.topbar-in {
  max-width: 1200px; margin: 0 auto;
  display: flex; align-items: center; justify-content: space-between;
}
.logo { display: flex; align-items: center; gap: .5rem; }
.logo-mark {
  font-size: 1rem; font-weight: 800; color: var(--accent);
  background: rgba(99,102,241,.12);
  padding: .15rem .5rem; border-radius: 6px;
  letter-spacing: -.02em;
}
.logo-txt { font-size: 1.05rem; font-weight: 700; letter-spacing: -.02em; }
.ver { color: var(--tx3); font-size: .78rem; }
.topbar-r { display: flex; align-items: center; gap: 1rem; }
.topbar-meta { color: var(--tx3); font-size: .78rem; }

/* ─── Main ─── */
main {
  max-width: 1200px; margin: 0 auto;
  padding: 1.25rem 1.5rem;
  display: flex; flex-direction: column; gap: 1.15rem;
}

/* ─── Hero ─── */
.hero {
  display: grid;
  grid-template-columns: 300px 1fr;
  grid-template-rows: auto auto;
  gap: 1.25rem 2rem;
  background: var(--card);
  border: 1px solid var(--bdr);
  border-radius: var(--r);
  padding: 1.75rem 2rem;
}
.hero-gauge {
  grid-row: 1 / 3;
  display: flex; flex-direction: column; align-items: center;
  justify-content: center;
}
.gauge-svg { width: 100%; max-width: 300px; }
.hero-grade {
  font-size: 1.4rem; font-weight: 800;
  margin-top: -.25rem; letter-spacing: .04em;
}
.hero-info {
  display: flex; flex-direction: column; gap: .4rem; padding-top: .5rem;
}
.hi-label {
  display: inline-block; min-width: 50px;
  font-size: .72rem; color: var(--tx3);
  text-transform: uppercase; letter-spacing: .06em;
}
.hi-dim { color: var(--tx3); font-size: .82rem; margin-left: .3rem; }
.hero-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: .75rem;
}
.stat-card {
  background: rgba(39,39,42,.25);
  border: 1px solid var(--bdr);
  border-radius: 10px;
  padding: .85rem 1rem;
}
.stat-value {
  font-size: 1.35rem; font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.stat-value-sm { font-size: .92rem; word-break: break-all; }
.stat-label {
  font-size: .68rem; color: var(--tx3);
  text-transform: uppercase; letter-spacing: .06em;
  margin-top: .2rem;
}
.stat-bar {
  height: 3px; background: var(--bdr);
  border-radius: 2px; margin-top: .45rem; overflow: hidden;
}
.stat-bar-fill { height: 100%; border-radius: 2px; }

/* ─── Cards ─── */
.card {
  background: var(--card);
  border: 1px solid var(--bdr);
  border-radius: var(--r);
  padding: 1.4rem 1.5rem;
}
.card-hdr {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 1.15rem; padding-bottom: .65rem;
  border-bottom: 1px solid var(--bdr);
}
.card-hdr h2 { font-size: .95rem; font-weight: 650; letter-spacing: -.01em; }
.card-sub { font-size: .78rem; color: var(--tx3); }

/* ─── Category Bars ─── */
.cat-grid { display: flex; flex-direction: column; gap: .7rem; }
.cat-row {
  display: grid; grid-template-columns: 175px 1fr 48px;
  gap: .85rem; align-items: center;
}
.cat-info { display: flex; align-items: center; gap: .45rem; }
.cat-name { font-size: .88rem; }
.cat-weight {
  font-size: .65rem; color: var(--tx3);
  background: rgba(39,39,42,.6); padding: .08rem .38rem;
  border-radius: 4px; font-weight: 500;
}
.cat-bar {
  height: 22px; background: rgba(39,39,42,.45);
  border-radius: 999px; overflow: hidden;
}
.cat-fill {
  height: 100%; width: var(--fw, 0%);
  border-radius: 999px; background: var(--fc);
  transform-origin: left; transform: scaleX(0);
  animation: scaleIn .8s ease-out both;
  animation-delay: var(--d, 0s);
}
.cat-score {
  font-size: .9rem; font-weight: 700; text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ─── Scenario Cards ─── */
.sc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
  gap: .7rem;
}
.sc-card {
  background: rgba(39,39,42,.18);
  border: 1px solid var(--bdr);
  border-radius: 10px; overflow: hidden;
  transition: border-color .2s, background .2s;
}
.sc-card:hover { border-color: var(--bdr2); background: rgba(39,39,42,.32); }
.sc-bar { height: 3px; }
.sc-body { padding: .9rem 1rem; }
.sc-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: .3rem;
}
.sc-id {
  font-weight: 600; font-size: .88rem;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 180px;
}
.sc-score {
  font-size: 1.65rem; font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1.1; margin-bottom: .35rem;
  letter-spacing: -.02em;
}
.sc-pills { display: flex; flex-wrap: wrap; gap: .35rem; margin-bottom: .35rem; }
.pill {
  font-size: .68rem; color: var(--tx2);
  background: rgba(99,102,241,.08);
  border: 1px solid rgba(99,102,241,.18);
  padding: .1rem .45rem; border-radius: 999px;
}
.pill-warn {
  background: rgba(239,68,68,.08);
  border-color: rgba(239,68,68,.2);
  color: var(--red);
}
.sc-fails { display: flex; flex-wrap: wrap; gap: .25rem; }
.ftag {
  font-size: .62rem; color: var(--red);
  background: rgba(239,68,68,.08);
  border: 1px solid rgba(239,68,68,.18);
  padding: .06rem .35rem; border-radius: 4px;
  text-transform: uppercase; letter-spacing: .04em; font-weight: 600;
}

/* ─── Charts ─── */
.charts-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: 1.15rem;
}
.chart-c {
  display: flex; justify-content: center; align-items: center;
  padding: .5rem 0;
}
.radar-svg { width: 100%; max-width: 340px; }
.radar-poly { opacity: 0; animation: radarIn .6s ease-out .5s forwards; }
.latency-chart { width: 100%; }

/* ─── Tables ─── */
.tbl {
  width: 100%; border-collapse: collapse; font-size: .82rem;
}
.tbl th {
  text-align: left; padding: .55rem .75rem;
  color: var(--tx3); font-size: .72rem;
  text-transform: uppercase; letter-spacing: .05em;
  border-bottom: 2px solid var(--bdr); font-weight: 600;
}
.tbl td { padding: .45rem .75rem; border-bottom: 1px solid var(--bdr); }
.tbl tbody tr:hover { background: rgba(99,102,241,.03); }
.mfail { color: var(--red); }

/* ─── Failed Details ─── */
.fd {
  margin-bottom: .45rem;
  border: 1px solid var(--bdr); border-radius: 8px;
  overflow: hidden;
}
.fd summary {
  cursor: pointer; padding: .7rem 1rem;
  background: rgba(239,68,68,.03);
  display: flex; align-items: center; gap: .65rem;
  font-size: .88rem; list-style: none;
}
.fd summary::-webkit-details-marker { display: none; }
.fd summary::before {
  content: '\\25B6'; font-size: .6rem; color: var(--tx3);
  transition: transform .2s;
}
.fd[open] summary::before { transform: rotate(90deg); }
.fd summary:hover { background: rgba(239,68,68,.06); }
.fd[open] summary { border-bottom: 1px solid var(--bdr); }
.fd-score { margin-left: auto; color: var(--tx3); font-size: .82rem; }
.fd-body { padding: 1rem; }
.fd-body h4 {
  font-size: .82rem; color: var(--tx2); margin: .65rem 0 .4rem;
  font-weight: 600;
}
.fd-body h4:first-child { margin-top: 0; }
.fd-body ul { padding-left: 1.4rem; }
.fd-body li { font-size: .82rem; margin: .2rem 0; color: var(--tx2); }
.fd-tbl {
  width: 100%; border-collapse: collapse; font-size: .78rem; margin-top: .4rem;
}
.fd-tbl th, .fd-tbl td {
  padding: .3rem .55rem; text-align: left;
  border-bottom: 1px solid var(--bdr);
}
.fd-tbl th { color: var(--tx3); font-size: .7rem; text-transform: uppercase; }

/* ─── Badges ─── */
.badge-pass {
  background: rgba(16,185,129,.1); color: var(--green);
  padding: .15rem .55rem; border-radius: 999px;
  font-size: .72rem; font-weight: 650;
}
.badge-fail {
  background: rgba(239,68,68,.1); color: var(--red);
  padding: .15rem .55rem; border-radius: 999px;
  font-size: .72rem; font-weight: 650;
}

/* ─── Footer ─── */
footer {
  text-align: center; padding: 1.75rem 1rem;
  color: var(--tx3); font-size: .78rem;
  border-top: 1px solid var(--bdr); margin-top: .5rem;
}
.foot-sub { margin-top: .4rem; }
footer code { font-size: .72rem; }

/* ─── No data ─── */
.no-data { color: var(--tx3); text-align: center; padding: 2rem; font-size: .88rem; }

/* ─── Animations ─── */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes scaleIn {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
@keyframes gaugeReveal {
  from { stroke-dashoffset: 376.99; }
}
@keyframes dotReveal {
  to { opacity: 1; }
}
@keyframes radarIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}
.fade-in {
  animation: fadeUp .5s ease-out both;
  animation-delay: var(--d, 0s);
}
.gauge-fill { animation: gaugeReveal 1.5s ease-out .3s both; }
.gauge-dot  { opacity: 0; animation: dotReveal .3s ease-out 1.8s forwards; }

/* ─── Responsive ─── */
@media (max-width: 960px) {
  .hero { grid-template-columns: 1fr; }
  .hero-gauge { grid-row: auto; }
  .hero-stats { grid-template-columns: repeat(2, 1fr); }
  .charts-row { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
  main { padding: 1rem; }
  .hero { padding: 1.25rem; }
  .hero-stats { grid-template-columns: 1fr 1fr; }
  .cat-row { grid-template-columns: 120px 1fr 40px; gap: .5rem; }
  .sc-grid { grid-template-columns: 1fr; }
  .stat-value { font-size: 1.1rem; }
}

/* ─── Print ─── */
@media print {
  body { background: #fff; color: #111; }
  .topbar { position: static; background: #fff; backdrop-filter: none; border-color: #ddd; }
  .topbar-meta, .ver { color: #666; }
  .card, .hero, .stat-card, .sc-card { background: #fff; border-color: #ddd; }
  .fade-in { opacity: 1 !important; transform: none !important; animation: none !important; }
  .gauge-fill { animation: none !important; }
  .gauge-dot  { opacity: 1 !important; animation: none !important; }
  .cat-fill   { transform: scaleX(1) !important; animation: none !important; }
  .radar-poly { opacity: 1 !important; animation: none !important; }
  code { background: #f3f3f3; }
  footer { color: #666; border-color: #ddd; }
}
"""

# ---------------------------------------------------------------------------
# Embedded JS — score counter animation
# ---------------------------------------------------------------------------

_JS = """\
(function() {
  document.querySelectorAll('.counter').forEach(function(el) {
    var target = parseFloat(el.dataset.target) || 0;
    var dec = parseInt(el.dataset.decimals || '0', 10);
    var dur = 1500;
    var startT = 0;
    function tick(now) {
      if (!startT) startT = now;
      var p = Math.min((now - startT) / dur, 1);
      var e = 1 - Math.pow(1 - p, 3);
      el.textContent = (target * e).toFixed(dec);
      if (p < 1) requestAnimationFrame(tick);
    }
    setTimeout(function() { requestAnimationFrame(tick); }, 300);
  });
})();
"""

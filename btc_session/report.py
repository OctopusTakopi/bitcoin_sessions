"""Assemble the self-contained HTML report from analysis results + chart images."""
from __future__ import annotations
from datetime import date

from .config import REGIONS, RECENT_DAYS
from .analysis import RegimeResult, OIResult, SessionStat


def _sp(x: float) -> str:
    return f"{x:+.1f}%"


def _rank(stats: dict[str, SessionStat], key, reverse=True):
    return sorted(stats.values(), key=lambda s: getattr(s, key), reverse=reverse)


def regime_takeaway(rr: RegimeResult) -> str:
    """One-sentence, data-driven readout for a regime."""
    st = rr.stats
    by_full = _rank(st, "full_return")
    by_recent = _rank(st, "recent_return")
    by_buy = _rank(st, "recent_imbalance")
    return (f"Over the window <b>{by_full[0].region}</b> held up best "
            f"({_sp(by_full[0].full_return)}) and <b>{by_full[-1].region}</b> worst "
            f"({_sp(by_full[-1].full_return)}). Recently <b>{by_recent[0].region}</b> leads "
            f"({_sp(by_recent[0].recent_return)}) and the most aggressive net buying sits in "
            f"<b>{by_buy[0].region}</b> hours ({_sp(by_buy[0].recent_imbalance)}).")


def oi_headline(oi: OIResult) -> tuple[str, str]:
    """Return (tag, sentence) describing the recent price/OI regime."""
    s = oi.stats
    up_price = s["price_recent"] > 0
    up_oi = s["oi_recent"] > 0
    if up_price and not up_oi:
        return ("Short-covering", "the recent bounce came on <b>falling</b> open interest — "
                "positions closing, not fresh leveraged longs (classic short-covering).")
    if up_price and up_oi:
        return ("New longs", "the recent move came with <b>rising</b> open interest — "
                "fresh money opening positions, a healthier, conviction-led advance.")
    if not up_price and up_oi:
        return ("New shorts", "price fell while open interest <b>rose</b> — "
                "new short positions being opened into weakness.")
    return ("De-risking", "both price and open interest fell — leveraged longs being "
            "unwound / liquidated.")


def _tiles(stats: dict[str, SessionStat]) -> str:
    out = []
    for name, r in REGIONS.items():
        s = stats[name]
        cls = "up" if s.recent_return > 0 else "down"
        out.append(f"""<div class="tile">
      <div class="h"><span class="dot" style="background:{r.light}"></span>{name}
        <span class="off">{s.offset_label}</span></div>
      <div class="big">{_sp(s.full_return)}</div>
      <div class="row">last {RECENT_DAYS}d <span class="{cls}">{_sp(s.recent_return)}</span>
        · flow {_sp(s.recent_imbalance)}</div></div>""")
    return "\n".join(out)


def _region_css_vars() -> str:
    light = "; ".join(f"--{n.lower()}:{r.light}" for n, r in REGIONS.items())
    dark = "; ".join(f"--{n.lower()}:{r.dark}" for n, r in REGIONS.items())
    return light, dark


def _figure(title_imgs: dict, alt: str) -> str:
    return f"""<div class="card">
    <img class="only-l" alt="{alt}, light" src="data:image/png;base64,{title_imgs['light']}">
    <img class="only-d" alt="{alt}, dark" src="data:image/png;base64,{title_imgs['dark']}">
  </div>"""


def _takeaway_md(rr: RegimeResult) -> str:
    st = rr.stats
    bf = _rank(st, "full_return")
    br = _rank(st, "recent_return")
    bb = _rank(st, "recent_imbalance")
    return (f"Over the window **{bf[0].region}** held up best ({_sp(bf[0].full_return)}) and "
            f"**{bf[-1].region}** worst ({_sp(bf[-1].full_return)}). Recently "
            f"**{br[0].region}** leads ({_sp(br[0].recent_return)}) and the most aggressive "
            f"net buying sits in **{bb[0].region}** hours ({_sp(bb[0].recent_imbalance)}).")


def _md_table(rr: RegimeResult) -> str:
    rows = [f"| Region | Full window | Last {RECENT_DAYS}d | Recent flow |",
            "|--------|------------:|---------:|------------:|"]
    for name, r in REGIONS.items():
        s = rr.stats[name]
        rows.append(f"| {r.label} | {_sp(s.full_return)} | {_sp(s.recent_return)} "
                    f"| {_sp(s.recent_imbalance)} |")
    return "\n".join(rows)


def _md_picture(prefix: str, stub: str, alt: str) -> str:
    return (f'<picture>\n'
            f'  <source media="(prefers-color-scheme: dark)" srcset="{prefix}/{stub}_dark.png">\n'
            f'  <img alt="{alt}" src="{prefix}/{stub}_light.png">\n'
            f'</picture>')


def build_markdown(*, symbol: str, start: date, end: date, generated: date,
                   primary: RegimeResult, oi: OIResult,
                   compare: list[RegimeResult], image_prefix: str = "assets") -> str:
    """The full report as GitHub-flavoured markdown (theme-aware charts)."""
    P = image_prefix
    out = []
    out.append(f"> **{symbol}** spot + USD-M futures · Binance · "
               f"{start:%d %b} – {end:%d %b %Y} UTC · generated {generated:%Y-%m-%d}. "
               f"Regenerate with `python main.py`.")
    out.append("")

    # section 1 — primary session flow
    out.append(f"### 1 · Session flow — {primary.regime.title.lower()} "
               f"({primary.regime.hours_label})")
    out.append("")
    out.append(_md_picture(P, f"dashboard_{primary.regime.key}", "Session dashboard"))
    out.append("")
    out.append(_md_table(primary))
    out.append("")
    out.append(_takeaway_md(primary))
    out.append("")

    # section 2 — open interest
    if oi.available:
        tag, sentence = oi_headline(oi)
        sentence = sentence.replace("<b>", "**").replace("</b>", "**")
        s = oi.stats
        out.append("### 2 · Open interest & positioning")
        out.append("")
        out.append(_md_picture(P, "open_interest", "Price vs open interest and long/short ratios"))
        out.append("")
        out.append(f"**{tag}.** Over the last {RECENT_DAYS} days price moved "
                   f"{_sp(s['price_recent'])} while open interest moved {_sp(s['oi_recent'])} — "
                   f"{sentence} The all-account long/short ratio ran "
                   f"{s['ls_start']:.2f} → {s['ls_end']:.2f} (peak {s['ls_max']:.2f}) while "
                   f"top traders went {s['tt_start']:.2f} → {s['tt_end']:.2f}.")
        out.append("")

    # section 3 — window-regime comparison (regimes other than the primary)
    others = [rr for rr in compare if rr.regime.key != primary.regime.key]
    if others:
        n = "3" if oi.available else "2"
        out.append(f"### {n} · Window-regime comparison")
        out.append("")
        out.append("The regional signal is **highly sensitive to how you define a "
                   "\"session\"** — the open-interest read is not. The same data on "
                   "different clocks:")
        out.append("")
        for rr in others:
            out.append(f"#### {rr.regime.title} — {rr.regime.hours_label}")
            out.append("")
            out.append(_md_picture(P, f"dashboard_{rr.regime.key}",
                                   f"{rr.regime.title} dashboard"))
            out.append("")
            out.append(_md_table(rr))
            out.append("")
            out.append(_takeaway_md(rr))
            out.append("")

    # method & caveats
    n = "4" if oi.available else "3"
    offs = ", ".join(r.label for r in REGIONS.values())
    out.append(f"### {n} · Method & caveats")
    out.append("")
    out.append(f"Each hourly candle is tagged by the region whose local window it falls in, "
               f"using representative offsets ({offs}). \"Return\" sums log-returns of a "
               f"region's hours; \"flow\" is `(taker-buy − taker-sell) / volume` (positive = "
               f"market-buy orders lifting the offer). Open interest and long/short ratios come "
               f"from Binance USD-M futures `metrics`; OI is BTC-denominated so it reflects "
               f"positioning, not price.")
    out.append("")
    out.append(f"_Session windows overlap (crypto trades 24/7), so volume shares sum past 100% "
               f"and per-region attribution is coarse — read trends, not levels. Offsets are "
               f"representative (no per-country DST). Futures metrics are Binance-only. A "
               f"{(end - start).days + 1}-day sample is a regime snapshot, not a rule. "
               f"Not financial advice._")
    return "\n".join(out)


def build_html(*, symbol: str, start: date, end: date, generated: date,
               primary: RegimeResult, primary_imgs: dict,
               oi: OIResult, oi_imgs: dict | None,
               compare: list[tuple[RegimeResult, dict]]) -> str:
    light_vars, dark_vars = _region_css_vars()

    # --- OI section ---
    if oi.available:
        tag, sentence = oi_headline(oi)
        s = oi.stats
        oi_section = f"""
  <h2><span class="n">02</span>Open interest &amp; positioning</h2>
  <p class="sub">Futures open interest separates real accumulation (price up on rising OI)
  from short-covering (price up on falling OI), and long/short ratios show who is positioned how.</p>
  {_figure(oi_imgs, "Price vs open interest and long/short ratios")}
  <div class="verdict"><span class="tag">{tag}</span>
  <p>Over the last {RECENT_DAYS} days price moved {_sp(s['price_recent'])} while open interest
  moved {_sp(s['oi_recent'])} — {sentence} The all-account long/short ratio ran
  {s['ls_start']:.2f} → {s['ls_end']:.2f} (peak {s['ls_max']:.2f}) while top traders went
  {s['tt_start']:.2f} → {s['tt_end']:.2f}.</p></div>"""
    else:
        oi_section = ""

    # --- comparison section ---
    comp_blocks = []
    for i, (rr, imgs) in enumerate(compare):
        comp_blocks.append(f"""
  <h3>{rr.regime.title} — {rr.regime.hours_label}</h3>
  <p class="sub">{regime_takeaway(rr)}</p>
  {_figure(imgs, f"{rr.regime.title} session dashboard")}""")
    comp_section = "\n".join(comp_blocks)

    oi_num = "02" if oi.available else None
    comp_num = "03" if oi.available else "02"
    method_num = "04" if oi.available else "03"

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC Session Flow Analysis — {symbol}</title>
<style>
:root{{--surface:#f4f5f7;--card:#fff;--ink:#0b1220;--sec:#4a5568;--mut:#8a93a3;
--line:#e2e5ea;--oi:#c77b12;--good:#0f9b53;--bad:#d5473f;{light_vars};
--shadow:0 1px 2px rgba(11,18,32,.06),0 8px 24px rgba(11,18,32,.06);}}
@media(prefers-color-scheme:dark){{:root{{--surface:#141821;--card:#1b2029;--ink:#f2f4f8;
--sec:#aab3c2;--mut:#727b8a;--line:#252b36;--oi:#e0a94a;--good:#3ec27e;--bad:#e8695f;{dark_vars};
--shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);}}}}
:root[data-theme=dark]{{--surface:#141821;--card:#1b2029;--ink:#f2f4f8;--sec:#aab3c2;--mut:#727b8a;
--line:#252b36;--oi:#e0a94a;--good:#3ec27e;--bad:#e8695f;{dark_vars};
--shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);}}
:root[data-theme=light]{{--surface:#f4f5f7;--card:#fff;--ink:#0b1220;--sec:#4a5568;--mut:#8a93a3;
--line:#e2e5ea;--oi:#c77b12;--good:#0f9b53;--bad:#d5473f;{light_vars};
--shadow:0 1px 2px rgba(11,18,32,.06),0 8px 24px rgba(11,18,32,.06);}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--surface);color:var(--ink);line-height:1.6;
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:920px;margin:0 auto;padding:56px 24px 80px}}
.eyebrow{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--asia);font-weight:700;margin:0 0 14px}}
h1{{font-size:clamp(27px,4.3vw,42px);line-height:1.1;margin:0 0 16px;font-weight:800;letter-spacing:-.02em;text-wrap:balance}}
.lede{{font-size:19px;color:var(--sec);margin:0 0 8px;max-width:64ch}}
.meta{{font-size:13px;color:var(--mut);font-variant-numeric:tabular-nums;margin-top:18px}}
h2{{font-size:23px;font-weight:800;letter-spacing:-.01em;margin:52px 0 6px;text-wrap:balance}}
h2 .n{{color:var(--mut);font-weight:700;margin-right:12px;font-variant-numeric:tabular-nums}}
h3{{font-size:18px;font-weight:700;margin:34px 0 2px}}
.sub{{color:var(--sec);margin:0 0 22px;max-width:70ch}} p{{max-width:70ch}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}}
.card img{{display:block;width:100%;height:auto}}
.only-l{{display:block}}.only-d{{display:none}}
@media(prefers-color-scheme:dark){{.only-l{{display:none}}.only-d{{display:block}}}}
:root[data-theme=dark] .only-l{{display:none}}:root[data-theme=dark] .only-d{{display:block}}
:root[data-theme=light] .only-l{{display:block}}:root[data-theme=light] .only-d{{display:none}}
.verdict{{display:flex;gap:14px;align-items:flex-start;background:var(--card);border:1px solid var(--line);
border-left:4px solid var(--oi);border-radius:12px;padding:20px 22px;margin:22px 0;box-shadow:var(--shadow)}}
.verdict .tag{{font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--oi);white-space:nowrap;padding-top:2px}}
.verdict p{{margin:0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:24px 0}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}}
.tile .h{{display:flex;align-items:center;gap:8px;font-weight:700;font-size:15px}}
.tile .off{{color:var(--mut);font-weight:500;font-size:13px}}
.dot{{width:10px;height:10px;border-radius:50%;flex:none}}
.tile .big{{font-size:25px;font-weight:800;font-variant-numeric:tabular-nums;margin:8px 0 2px}}
.tile .row{{font-size:13px;color:var(--sec);font-variant-numeric:tabular-nums}}
.up{{color:var(--good)}}.down{{color:var(--bad)}}
hr{{border:none;border-top:1px solid var(--line);margin:44px 0}}
.foot{{font-size:12.5px;color:var(--mut);margin-top:10px}}
code{{background:var(--card);border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:.88em}}
</style></head><body>
<div class="wrap">
  <p class="eyebrow">Bitcoin · regional session flow analysis</p>
  <h1>How {symbol} trades across the world's market sessions</h1>
  <p class="lede">Every hour of price and futures data, split into the region whose market
  was open — measuring where return is earned, who is aggressively buying, where volume
  concentrates, and whether moves are backed by real leverage.</p>
  <p class="meta">{symbol} spot + USD-M futures · Binance · {start:%d %b} – {end:%d %b %Y} UTC
  · generated {generated:%Y-%m-%d}</p>

  <div class="grid">{_tiles(primary.stats)}</div>

  <h2><span class="n">01</span>Session flow — {primary.regime.title.lower()}</h2>
  <p class="sub">Windows use {primary.regime.hours_label} per region. {regime_takeaway(primary)}</p>
  {_figure(primary_imgs, "Primary session dashboard")}
{oi_section}

  <h2><span class="n">{comp_num}</span>Window-regime comparison</h2>
  <p class="sub">The result depends on how you define a "session". These three windows —
  the same data on three different clocks — show how robust each regional signal is.</p>
  {comp_section}

  <h2><span class="n">{method_num}</span>Method &amp; caveats</h2>
  <p>Each hourly candle is tagged by the region whose local window it falls in, using
  representative offsets: {", ".join(f'<span style="color:var(--{n.lower()});font-weight:700">{r.label}</span>' for n, r in REGIONS.items())}.
  "Return" sums log-returns of a region's hours; "flow" is
  <code>(taker-buy − taker-sell) / volume</code> (positive = market-buy orders lifting the offer).
  Open interest, long/short and top-trader ratios come from Binance USD-M futures
  <code>metrics</code>; OI is BTC-denominated so it reflects positioning, not price.</p>
  <p class="foot">Caveats: session windows overlap (crypto trades 24/7), so volume shares sum
  past 100% and per-region attribution is coarse — read trends, not absolute levels. Offsets are
  representative (no per-country DST). Futures metrics are Binance-only. A short sample is a regime
  snapshot, not a rule.</p>
</div></body></html>
"""

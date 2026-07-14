#!/usr/bin/env python3
"""BTC Session Flow Analysis — entry point.

Downloads (and caches) Binance BTC spot + futures data, splits it into regional
market sessions, and writes a self-contained HTML report to ``output/``.

Usage
-----
    python main.py                         # last 60 days, default settings
    python main.py --days 90               # longer window
    python main.py --symbol ETHUSDT        # a different market
    python main.py --regime institutional  # change the primary session window
    python main.py --refresh               # ignore cache, re-download
    python main.py --end 2026-06-30        # analyse up to a specific date

All data is cached under ``data/`` and reused on the next run.
"""
from __future__ import annotations
import argparse
import shutil
from datetime import date, timedelta
from pathlib import Path

from btc_session import config
from btc_session.data import load_klines, load_metrics
from btc_session.analysis import build_hourly, analyze_regime, analyze_oi
from btc_session import charts
from btc_session.report import build_html, build_markdown, oi_headline

ROOT = Path(__file__).resolve().parent
README_START = "<!-- REPORT:START -->"
README_END = "<!-- REPORT:END -->"


def inject_readme(readme: Path, markdown: str):
    """Replace the content between the report markers in README.md."""
    if not readme.exists():
        return
    text = readme.read_text()
    if README_START not in text or README_END not in text:
        return
    head = text[: text.index(README_START) + len(README_START)]
    tail = text[text.index(README_END):]
    readme.write_text(f"{head}\n\n{markdown}\n\n{tail}")


def parse_args():
    p = argparse.ArgumentParser(description="BTC regional session flow analysis")
    p.add_argument("--symbol", default=config.SYMBOL, help="trading pair (default BTCUSDT)")
    p.add_argument("--days", type=int, default=config.LOOKBACK_DAYS,
                   help=f"lookback window in days (default {config.LOOKBACK_DAYS})")
    p.add_argument("--end", type=lambda s: date.fromisoformat(s), default=None,
                   help="last date to analyse, YYYY-MM-DD (default: yesterday)")
    p.add_argument("--regime", default=config.DEFAULT_REGIME, choices=list(config.REGIMES),
                   help=f"primary session window (default {config.DEFAULT_REGIME})")
    p.add_argument("--data-dir", type=Path, default=ROOT / "data")
    p.add_argument("--output-dir", type=Path, default=ROOT / "output")
    p.add_argument("--refresh", action="store_true", help="ignore cache and re-download")
    return p.parse_args()


def main():
    args = parse_args()
    end = args.end or (date.today() - timedelta(days=1))
    start = end - timedelta(days=args.days - 1)
    print(f"BTC Session Analysis · {args.symbol} · {start} → {end} "
          f"· primary regime: {args.regime}")

    # 1. data (cached under data/) -----------------------------------------
    print("Loading data …")
    klines = load_klines(args.symbol, config.INTERVAL, start, end,
                         args.data_dir, refresh=args.refresh)
    metrics = load_metrics(args.symbol, start, end, args.data_dir, refresh=args.refresh)
    hourly = build_hourly(klines)
    print(f"  {len(hourly)} hourly candles "
          f"({hourly['t'].min():%Y-%m-%d} → {hourly['t'].max():%Y-%m-%d} UTC)")

    # 2. analysis ----------------------------------------------------------
    regimes = {k: analyze_regime(hourly, config.REGIMES[k])
               for k in config.COMPARE_REGIMES}
    if args.regime not in regimes:
        regimes[args.regime] = analyze_regime(hourly, config.REGIMES[args.regime])
    primary = regimes[args.regime]
    oi = analyze_oi(metrics, hourly)

    # 3. charts (embed base64, also save light/dark PNGs to output/) --------
    print("Rendering charts …")
    charts_dir = args.output_dir / "charts"
    imgs_by_regime = {
        k: charts.render_both(charts.dashboard, rr, args.symbol,
                              out_stub=charts_dir / f"dashboard_{k}")
        for k, rr in regimes.items()
    }
    oi_imgs = (charts.render_both(charts.open_interest, oi, args.symbol,
                                  out_stub=charts_dir / "open_interest")
               if oi.available else None)

    # 4. report ------------------------------------------------------------
    html = build_html(
        symbol=args.symbol, start=start, end=end, generated=date.today(),
        primary=primary, primary_imgs=imgs_by_regime[args.regime],
        oi=oi, oi_imgs=oi_imgs,
        compare=[(regimes[k], imgs_by_regime[k]) for k in config.COMPARE_REGIMES],
    )
    out = args.output_dir / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)

    # publish charts used by the markdown report into committed assets/, then
    # write output/report.md and refresh the README's report section.
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    stubs = [f"dashboard_{k}" for k in config.COMPARE_REGIMES]
    if oi.available:
        stubs.append("open_interest")
    for stub in stubs:
        for theme in ("light", "dark"):
            src = charts_dir / f"{stub}_{theme}.png"
            if src.exists():
                shutil.copyfile(src, assets / f"{stub}_{theme}.png")

    compare_results = [regimes[k] for k in config.COMPARE_REGIMES]
    md_common = dict(symbol=args.symbol, start=start, end=end, generated=date.today(),
                     primary=primary, oi=oi, compare=compare_results)
    (args.output_dir / "report.md").write_text(
        build_markdown(**md_common, image_prefix="../assets"))
    inject_readme(ROOT / "README.md",
                  build_markdown(**md_common, image_prefix="assets"))

    # 5. console summary ---------------------------------------------------
    print("\nSession returns (primary regime):")
    for name, s in primary.stats.items():
        print(f"  {name:7s} {s.offset_label:6s} full {s.full_return:+6.1f}%  "
              f"recent {s.recent_return:+6.1f}%  flow {s.recent_imbalance:+5.1f}%")
    if oi.available:
        tag, _ = oi_headline(oi)
        st = oi.stats
        print(f"Open interest: recent price {st['price_recent']:+.1f}% vs "
              f"OI {st['oi_recent']:+.1f}%  → {tag}")
    print(f"\nReport:  {out}")
    print(f"Charts:  {charts_dir}/  ·  Data cache: {args.data_dir}/")


if __name__ == "__main__":
    main()

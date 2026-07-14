#!/usr/bin/env python3
"""Since-inception session returns for Binance BTC USD-M perpetual futures.

Downloads MONTHLY 1h futures klines (BTCUSDT, from 2020-01) and computes the
cumulative return earned during each regional session — testing whether Asian
hours structurally lose more than US hours over the full history.

Run:  python scripts/inception_analysis.py
Output: output/inception_sessions.png  +  a printed summary table.
"""
from __future__ import annotations
import io
import sys
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from btc_session.config import REGIONS, REGIMES                      # noqa: E402
from btc_session.data import KLINE_COLS, _to_utc, _read_zip_csv, _UA  # noqa: E402
from btc_session.analysis import build_hourly, region_utc_hours      # noqa: E402

SYMBOL = "BTCUSDT"
START = pd.Period("2020-01", "M")     # first available monthly futures file
BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
CACHE = ROOT / "data" / "raw" / "klines_um_monthly" / SYMBOL / "1h"
OUT = ROOT / "output" / "inception_sessions.png"


def download_months() -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    end = pd.Period.now("M")
    frames, months = [], []
    p = START
    while p <= end:
        ym = f"{p.year}-{p.month:02d}"
        fn = f"{SYMBOL}-1h-{ym}.zip"
        dest = CACHE / fn
        if not (dest.exists() and dest.stat().st_size > 0):
            url = f"{BASE}/{SYMBOL}/1h/{fn}"
            try:
                req = urllib.request.Request(url, headers=_UA)
                dest.write_bytes(urllib.request.urlopen(req, timeout=60).read())
            except urllib.error.HTTPError as e:
                if e.code == 404:          # month not yet published
                    p += 1
                    continue
                raise
        df = _read_zip_csv(dest, header=None, names=KLINE_COLS)
        # Newer monthly files carry a header row; older ones don't. Drop any
        # non-numeric (header) rows before parsing.
        df = df[pd.to_numeric(df["open_time"], errors="coerce").notna()].copy()
        df["open_time"] = df["open_time"].astype("int64")
        # Parse timestamps PER FILE — the epoch unit switched ms->us in 2025,
        # so a whole-range parse would misread the newer rows.
        df["t"] = _to_utc(df["open_time"])
        frames.append(df)
        months.append(ym)
        p += 1
    print(f"loaded {len(months)} monthly files: {months[0]} .. {months[-1]}")
    raw = pd.concat(frames, ignore_index=True)
    raw = raw.sort_values("t").drop_duplicates("t").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume", "taker_buy_base"):
        raw[c] = raw[c].astype(float)
    return raw


def main():
    raw = download_months()
    hourly = build_hourly(raw)
    print(f"{len(hourly):,} hourly candles  {hourly['t'].min():%Y-%m-%d} "
          f"-> {hourly['t'].max():%Y-%m-%d} UTC")

    # cumulative GROWTH multiple per session, for every regime
    results = {}
    for rk, regime in REGIMES.items():
        curves, totals = {}, {}
        for name, region in REGIONS.items():
            hours = region_utc_hours(region.utc_offset, regime)
            sub = hourly[hourly["hour"].isin(hours)]
            daily_ret = sub.groupby("date")["ret"].sum()
            growth = np.exp(daily_ret.cumsum())          # $1 -> multiple
            curves[name] = growth
            totals[name] = (growth.iloc[-1] - 1) * 100    # total % return
        results[rk] = (curves, totals)

    # ---- chart: one panel per regime, log-scale equity curves ----
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.6), sharey=True)
    ink, mut, grid, axis = "#0b1220", "#8a93a3", "#e2e5ea", "#c3c8d2"
    for ax, rk in zip(axes, REGIMES):
        curves, totals = results[rk]
        for name, region in REGIONS.items():
            ax.plot(curves[name].index, curves[name], color=region.light, lw=1.8,
                    label=f"{name}  {totals[name]:+,.0f}%")
        ax.set_yscale("log")
        ax.set_title(f"{REGIMES[rk].title} ({REGIMES[rk].hours_label})",
                     fontsize=12, fontweight="bold", color=ink, loc="left")
        ax.legend(frameon=False, fontsize=9, loc="upper left")
        ax.grid(True, which="both", color=grid, lw=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(axis)
        ax.tick_params(colors=mut, labelsize=9)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0].set_ylabel("growth of $1 during session hours (log)")
    fig.suptitle(f"{SYMBOL} USD-M perpetual — cumulative return by regional session "
                 f"since inception ({hourly['t'].min():%b %Y}–{hourly['t'].max():%b %Y})",
                 fontsize=14, fontweight="bold", color=ink, x=0.5, y=1.02)
    fig.text(0.5, -0.03, "Binance futures monthly 1h klines · session = local hours per region "
             "· log y-axis", ha="center", color=mut, fontsize=9)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=140, bbox_inches="tight", facecolor="white")
    print(f"\nsaved {OUT}")

    # ---- summary table ----
    print("\nTotal return by session over full history (Asia vs US):")
    print(f"  {'regime':16s} {'Asia':>10s} {'UAE':>10s} {'Europe':>10s} {'US':>10s}   Asia−US")
    asia_worse = 0
    for rk in REGIMES:
        _, t = results[rk]
        gap = t["Asia"] - t["US"]
        asia_worse += gap < 0
        print(f"  {REGIMES[rk].title:16s} {t['Asia']:+9.0f}% {t['UAE']:+9.0f}% "
              f"{t['Europe']:+9.0f}% {t['US']:+9.0f}%   {gap:+,.0f}pp")
    print(f"\nAsia underperformed US in {asia_worse}/{len(REGIMES)} window regimes.")


if __name__ == "__main__":
    main()

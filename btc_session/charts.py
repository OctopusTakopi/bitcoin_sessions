"""Matplotlib figures, theme-matched (light + dark), returned as base64 PNGs."""
from __future__ import annotations
import io
import base64
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

from .config import REGIONS, RECENT_DAYS
from .analysis import RegimeResult, OIResult, cumulative_return

LIGHT = dict(surface="#f4f5f7", ink="#0b1220", sec="#4a5568", mut="#8a93a3",
             grid="#e2e5ea", axis="#c3c8d2", key="light", oi="#c77b12", pxc="#0b1220")
DARK = dict(surface="#141821", ink="#f2f4f8", sec="#aab3c2", mut="#727b8a",
            grid="#252b36", axis="#39414f", key="dark", oi="#e0a94a", pxc="#f2f4f8")


def _color(region_name: str, th: dict) -> str:
    r = REGIONS[region_name]
    return r.dark if th["key"] == "dark" else r.light


def _setrc(th: dict):
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "text.color": th["ink"], "axes.labelcolor": th["sec"],
        "xtick.color": th["mut"], "ytick.color": th["mut"]})


def _style(fig, axes, th, xmax):
    for ax in axes:
        ax.set_facecolor(th["surface"])
        ax.grid(axis="y", color=th["grid"], lw=0.7)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(th["axis"])
        ax.tick_params(colors=th["mut"], labelsize=9)
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.set_xlim(right=xmax)
    fig.patch.set_facecolor(th["surface"])


def _place(ax, x, entries, th):
    """Draw right-edge labels, nudged apart so they don't overlap."""
    entries = sorted(entries, key=lambda e: e[0])
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * 0.06
    ys = [e[0] for e in entries]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] < gap:
            ys[i] = ys[i - 1] + gap
    for (yv, txt, c), y in zip(entries, ys):
        ax.annotate(f" {txt}", (x, yv), xytext=(x, y), color=c,
                    fontsize=9, fontweight="bold", va="center")


def _b64(fig, save: Path | None) -> str:
    if save:
        save.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


_pct0 = FuncFormatter(lambda v, _: f"{v:+.0f}%")
_pctv = FuncFormatter(lambda v, _: f"{v:.0f}%")


# ----------------------------------------------------------------------------
def dashboard(rr: RegimeResult, th: dict, save: Path | None = None) -> str:
    """3-panel session dashboard: return, buy/sell imbalance, volume share."""
    _setrc(th)
    idx = rr.index
    xmax = idx.max() + pd.Timedelta(days=6)
    fig, (a, b, c) = plt.subplots(3, 1, figsize=(11, 12),
                                  gridspec_kw={"height_ratios": [1.5, 1, 1], "hspace": 0.34})

    for name in REGIONS:
        cc = _color(name, th)
        cum = cumulative_return(rr.daily[name])
        a.plot(idx, cum, color=cc, lw=2, label=REGIONS[name].label)
        a.plot(idx[-1], cum.iloc[-1], "o", color=cc, ms=6, mec=th["surface"], mew=1.5)
    a.axhline(0, color=th["axis"], lw=1)
    _place(a, idx[-1], [(cumulative_return(rr.daily[n]).iloc[-1],
                         f"{rr.stats[n].full_return:+.1f}%", _color(n, th)) for n in REGIONS], th)
    a.set_title(f"Return earned during each region's {rr.regime.title.lower()} "
                f"({rr.regime.hours_label})", fontsize=13, fontweight="bold",
                color=th["ink"], loc="left", pad=8)
    a.set_ylabel("cumulative return")
    a.yaxis.set_major_formatter(_pct0)
    a.legend(loc="lower left", frameon=False, fontsize=9, ncol=4, labelcolor=th["sec"])

    endB = []
    for name in REGIONS:
        cc = _color(name, th)
        s = rr.daily[name]["imb"].rolling(7, min_periods=3).mean() * 100
        b.plot(idx, s, color=cc, lw=2)
        endB.append((s.iloc[-1], name, cc))
    b.axhline(0, color=th["axis"], lw=1)
    _place(b, idx[-1], endB, th)
    b.set_title("Spot aggressive buy / sell imbalance (7-day rolling)",
                fontsize=13, fontweight="bold", color=th["ink"], loc="left", pad=8)
    b.set_ylabel("net taker buying")
    b.yaxis.set_major_formatter(_pct0)

    endC = []
    for name in REGIONS:
        cc = _color(name, th)
        s = (rr.daily[name]["vol"] / rr.total_volume * 100).rolling(7, min_periods=3).mean()
        c.plot(idx, s, color=cc, lw=2)
        endC.append((s.iloc[-1], name, cc))
    _place(c, idx[-1], endC, th)
    c.set_title("Share of daily traded volume (7-day rolling)",
                fontsize=13, fontweight="bold", color=th["ink"], loc="left", pad=8)
    c.set_ylabel("volume share")
    c.yaxis.set_major_formatter(_pctv)
    c.text(0.005, 0.05, rr.regime.note, transform=c.transAxes,
           fontsize=8.5, color=th["mut"], style="italic")

    _style(fig, (a, b, c), th, xmax)
    return _b64(fig, save)


# ----------------------------------------------------------------------------
def open_interest(oi: OIResult, th: dict, save: Path | None = None) -> str:
    """2-panel OI verification: price vs OI (indexed) + long/short ratios."""
    _setrc(th)
    price, oih = oi.price, oi.oi
    idx_end = price.index[-1]
    xmax = idx_end + pd.Timedelta(days=6)
    recent_start = idx_end - pd.Timedelta(days=RECENT_DAYS)
    fig, (a, b) = plt.subplots(2, 1, figsize=(11, 8.6),
                               gridspec_kw={"height_ratios": [1.25, 1], "hspace": 0.32})

    for ax in (a, b):
        ax.axvspan(price.index[0], recent_start, color=th["mut"], alpha=0.05)
        ax.axvspan(recent_start, xmax, color="#eb6834", alpha=0.07)
        ax.axvline(recent_start, color=th["axis"], lw=1, ls=(0, (4, 3)))

    pxi = price / price.iloc[0] * 100
    oii = oih / oih.iloc[0] * 100
    a.plot(pxi.index, pxi, color=th["pxc"], lw=2.4)
    a.plot(oii.index, oii, color=th["oi"], lw=2.4)
    a.axhline(100, color=th["axis"], lw=1)
    _place(a, pxi.index[-1], [(pxi.iloc[-1], "BTC price", th["pxc"]),
                              (oii.iloc[-1], "Open interest", th["oi"])], th)
    a.set_title("Price vs Open Interest (indexed to 100) — is the move real buying?",
                fontsize=13, fontweight="bold", color=th["ink"], loc="left", pad=8)
    a.set_ylabel("indexed (start = 100)")

    b.plot(oi.ls_accounts.index, oi.ls_accounts, color=_color("Asia", th), lw=2.4)
    b.plot(oi.ls_top.index, oi.ls_top, color=_color("US", th), lw=2.4)
    b.axhline(1.0, color=th["axis"], lw=1.2, ls=(0, (4, 3)))
    _place(b, oi.ls_accounts.index[-1],
           [(oi.ls_accounts.iloc[-1], "All accounts", _color("Asia", th)),
            (oi.ls_top.iloc[-1], "Top traders", _color("US", th))], th)
    b.set_title("Long / short ratio (>1 = net long) — who is positioned how",
                fontsize=13, fontweight="bold", color=th["ink"], loc="left", pad=8)
    b.set_ylabel("long / short ratio")
    b.text(0.005, 0.05, f"shaded = last {RECENT_DAYS} days",
           transform=b.transAxes, fontsize=8.5, color=th["mut"], style="italic")

    _style(fig, (a, b), th, xmax)
    return _b64(fig, save)


def render_both(fn, *args, out_stub: Path | None = None) -> dict:
    """Render a figure fn in both themes; save light PNG to ``out_stub`` if given."""
    return {
        "light": fn(*args, LIGHT, save=(out_stub.with_name(out_stub.name + "_light.png")
                                        if out_stub else None)),
        "dark": fn(*args, DARK, save=(out_stub.with_name(out_stub.name + "_dark.png")
                                      if out_stub else None)),
    }

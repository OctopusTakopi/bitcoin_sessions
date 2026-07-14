"""Turn raw klines / metrics into per-session statistics and OI positioning."""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import REGIONS, REGIMES, Regime, RECENT_DAYS


# ----------------------------------------------------------------------------
# session windows
# ----------------------------------------------------------------------------
def region_utc_hours(offset: int, regime: Regime) -> list[int]:
    """UTC hours covered by a region's local ``[start, end)`` window."""
    return [(h - offset) % 24 for h in range(regime.start, regime.end)]


# ----------------------------------------------------------------------------
# hourly base frame
# ----------------------------------------------------------------------------
def build_hourly(klines: pd.DataFrame) -> pd.DataFrame:
    df = klines.copy()
    df["ret"] = np.log(df["close"] / df["open"])          # per-hour log return
    df["taker_sell_base"] = df["volume"] - df["taker_buy_base"]
    df["hour"] = df["t"].dt.hour
    df["date"] = df["t"].dt.normalize()
    return df


# ----------------------------------------------------------------------------
# per-session daily aggregates + summary stats
# ----------------------------------------------------------------------------
@dataclass
class SessionStat:
    region: str
    offset_label: str
    full_return: float        # % over full window
    recent_return: float      # % over last RECENT_DAYS
    recent_imbalance: float   # % net taker buying, last RECENT_DAYS


def session_daily(hourly: pd.DataFrame, utc_hours: list[int]) -> pd.DataFrame:
    """Daily aggregates for the hours belonging to one session."""
    sub = hourly[hourly["hour"].isin(utc_hours)]
    g = sub.groupby("date").agg(
        ret=("ret", "sum"),
        vol=("volume", "sum"),
        buy=("taker_buy_base", "sum"),
        sell=("taker_sell_base", "sum"),
    )
    g["imb"] = (g["buy"] - g["sell"]) / g["vol"]
    return g


def cumulative_return(daily: pd.DataFrame) -> pd.Series:
    return (np.exp(daily["ret"].cumsum()) - 1) * 100


def _ret_pct(daily: pd.DataFrame, tail: int | None = None) -> float:
    r = daily["ret"] if tail is None else daily["ret"].iloc[-tail:]
    return (np.exp(r.sum()) - 1) * 100


@dataclass
class RegimeResult:
    regime: Regime
    daily: dict[str, pd.DataFrame]           # region -> daily frame
    stats: dict[str, SessionStat]
    total_volume: pd.Series                  # daily total across 24h
    index: pd.DatetimeIndex


def analyze_regime(hourly: pd.DataFrame, regime: Regime) -> RegimeResult:
    daily, stats = {}, {}
    for name, region in REGIONS.items():
        hours = region_utc_hours(region.utc_offset, regime)
        g = session_daily(hourly, hours)
        daily[name] = g
        stats[name] = SessionStat(
            region=name,
            offset_label=region.label.split("(")[1].rstrip(")"),
            full_return=_ret_pct(g),
            recent_return=_ret_pct(g, RECENT_DAYS),
            recent_imbalance=g["imb"].iloc[-RECENT_DAYS:].mean() * 100,
        )
    total_volume = hourly.groupby("date")["volume"].sum()
    index = daily[next(iter(REGIONS))].index
    return RegimeResult(regime, daily, stats, total_volume, index)


def analyze_all_regimes(hourly: pd.DataFrame,
                        regime_keys: list[str]) -> dict[str, RegimeResult]:
    return {k: analyze_regime(hourly, REGIMES[k]) for k in regime_keys}


# ----------------------------------------------------------------------------
# open interest & positioning
# ----------------------------------------------------------------------------
@dataclass
class OIResult:
    available: bool
    price: pd.Series = None            # hourly close, indexed by time
    oi: pd.Series = None               # hourly open interest (BTC)
    ls_accounts: pd.Series = None      # daily long/short ratio, all accounts
    ls_top: pd.Series = None           # daily long/short ratio, top traders
    stats: dict = None


def analyze_oi(metrics: pd.DataFrame, hourly: pd.DataFrame) -> OIResult:
    if metrics.empty or "sum_open_interest" not in metrics.columns:
        return OIResult(available=False)

    m = metrics.set_index("t")
    oi = m["sum_open_interest"].resample("1h").last()
    ls = m["count_long_short_ratio"].resample("1D").mean()
    tt = m["sum_toptrader_long_short_ratio"].resample("1D").mean()

    price = hourly.set_index("t")["close"]
    oi_h = oi.reindex(price.index).ffill().bfill()
    recent_start = price.index[-1] - pd.Timedelta(days=RECENT_DAYS)

    def pct(s, mask=None):
        s = s[mask] if mask is not None else s
        return (s.iloc[-1] / s.iloc[0] - 1) * 100

    rmask = price.index >= recent_start
    stats = {
        "price_full": pct(price),
        "oi_full": pct(oi_h),
        "price_recent": pct(price, rmask),
        "oi_recent": pct(oi_h, rmask),
        "ls_start": ls.iloc[0], "ls_end": ls.iloc[-1], "ls_max": ls.max(),
        "tt_start": tt.iloc[0], "tt_end": tt.iloc[-1],
    }
    return OIResult(True, price, oi_h, ls, tt, stats)

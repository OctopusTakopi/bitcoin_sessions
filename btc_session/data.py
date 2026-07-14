"""Download and cache Binance public market data under the local ``data/`` folder.

Data source: https://data.binance.vision/  (no API key required).

Two datasets are used:
  * spot 1h klines            -> price / volume / taker-buy flow
  * USD-M futures ``metrics`` -> open interest and long/short positioning

Raw daily ``.zip`` files are cached under ``data/raw/`` and never re-downloaded.
The assembled per-range frame is cached as parquet under ``data/processed/``.
"""
from __future__ import annotations
import io
import zipfile
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .config import BINANCE_BASE

_UA = {"User-Agent": "Mozilla/5.0 (btc-session-analysis)"}

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
              "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _download(url: str, dest: Path) -> bool:
    """Download ``url`` to ``dest``. Returns False on 404 (data not yet published)."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return True


def _read_zip_csv(path: Path, **kw) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        name = zf.namelist()[0]
        return pd.read_csv(io.BytesIO(zf.read(name)), **kw)


def _to_utc(series: pd.Series) -> pd.Series:
    """Parse Binance epoch timestamps, auto-detecting s / ms / us resolution.

    Binance switched kline timestamps to microseconds in 2025-2026; older data
    is milliseconds. Detect by magnitude so any date range parses correctly.
    """
    v = float(series.iloc[0])
    unit = "us" if v > 1e15 else "ms" if v > 1e12 else "s"
    return pd.to_datetime(series, unit=unit, utc=True)


# ----------------------------------------------------------------------------
# public loaders
# ----------------------------------------------------------------------------
def load_klines(symbol: str, interval: str, start: date, end: date,
                data_dir: Path, refresh: bool = False) -> pd.DataFrame:
    """Return hourly spot klines for ``[start, end]`` (UTC-indexed), cached locally."""
    cache = data_dir / "processed" / f"klines_{symbol}_{interval}_{start}_{end}.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)

    raw_dir = data_dir / "raw" / "klines" / symbol / interval
    frames, missing = [], []
    for d in daterange(start, end):
        fn = f"{symbol}-{interval}-{d}.zip"
        url = f"{BINANCE_BASE}/data/spot/daily/klines/{symbol}/{interval}/{fn}"
        dest = raw_dir / fn
        if _download(url, dest):
            frames.append(_read_zip_csv(dest, header=None, names=KLINE_COLS))
        else:
            missing.append(str(d))
    if not frames:
        raise RuntimeError(f"No kline data downloaded for {symbol} {start}..{end}")
    if missing:
        print(f"  klines: {len(frames)} days ({len(missing)} not yet published: "
              f"{', '.join(missing)})")

    df = pd.concat(frames, ignore_index=True)
    df["t"] = _to_utc(df["open_time"])
    df = df.sort_values("t").drop_duplicates("t").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume", "taker_buy_base", "quote_volume"):
        df[c] = df[c].astype(float)
    df = df[["t", "open", "high", "low", "close", "volume", "quote_volume",
             "taker_buy_base"]]
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def load_metrics(symbol: str, start: date, end: date,
                 data_dir: Path, refresh: bool = False) -> pd.DataFrame:
    """Return USD-M futures metrics (open interest, long/short) for the range.

    Cached locally. Returns an empty frame if the dataset is unavailable for the
    symbol/range (analysis then simply skips the open-interest section).
    """
    cache = data_dir / "processed" / f"metrics_{symbol}_{start}_{end}.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)

    raw_dir = data_dir / "raw" / "metrics" / symbol
    frames = []
    for d in daterange(start, end):
        fn = f"{symbol}-metrics-{d}.zip"
        url = f"{BINANCE_BASE}/data/futures/um/daily/metrics/{symbol}/{fn}"
        dest = raw_dir / fn
        if _download(url, dest):
            frames.append(_read_zip_csv(dest))
    if not frames:
        print("  metrics: none available — open-interest section will be skipped")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["t"] = pd.to_datetime(df["create_time"], utc=True)
    df = df.sort_values("t").drop_duplicates("t").reset_index(drop=True)
    keep = ["t", "sum_open_interest", "sum_open_interest_value",
            "count_long_short_ratio", "sum_toptrader_long_short_ratio",
            "sum_taker_long_short_vol_ratio"]
    df = df[[c for c in keep if c in df.columns]]
    for c in df.columns:
        if c != "t":
            df[c] = df[c].astype(float)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df

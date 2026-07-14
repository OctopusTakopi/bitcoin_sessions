"""Static configuration: regions, session-window regimes, colors, defaults."""
from __future__ import annotations
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# Data defaults
# ----------------------------------------------------------------------------
SYMBOL = "BTCUSDT"
INTERVAL = "1h"
LOOKBACK_DAYS = 60          # default analysis window length
BINANCE_BASE = "https://data.binance.vision"


# ----------------------------------------------------------------------------
# Regions — a representative UTC offset and a color per theme
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Region:
    name: str
    utc_offset: int          # representative offset, e.g. Asia = UTC+8
    light: str
    dark: str

    @property
    def label(self) -> str:
        sign = "+" if self.utc_offset >= 0 else "-"
        return f"{self.name} (UTC{sign}{abs(self.utc_offset)})"


# Order matters: it drives legend order and color assignment.
REGIONS: dict[str, Region] = {
    "Asia":   Region("Asia",   8,  "#2a78d6", "#3987e5"),   # Tokyo/HK/Singapore
    "UAE":    Region("UAE",    4,  "#4a3aa7", "#9085e9"),   # Dubai
    "Europe": Region("Europe", 1,  "#1baf7a", "#199e70"),   # London/Frankfurt
    "US":     Region("US",    -4,  "#eb6834", "#d95926"),   # New York (EDT)
}


# ----------------------------------------------------------------------------
# Session regimes — a local-hour window applied to every region.
# UTC hours are derived per-region from the offset (see analysis.region_utc_hours).
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Regime:
    key: str
    title: str
    start: int               # local hour, inclusive
    end: int                 # local hour, exclusive
    note: str

    @property
    def hours_label(self) -> str:
        return f"{self.start:02d}:00–{self.end:02d}:00 local"


REGIMES: dict[str, Regime] = {
    "retail": Regime(
        "retail", "Retail hours", 8, 22,
        "retail windows are 14h and overlap heavily — read the trend, not the level"),
    "institutional": Regime(
        "institutional", "Institutional hours", 9, 17,
        "institutional windows are 8h — less overlap, sharper regional separation"),
    "exchange": Regime(
        "exchange", "Exchange hours", 10, 16,
        "narrow exchange windows (6h) isolate each region's core session"),
}

DEFAULT_REGIME = "retail"
# Regimes rendered in the side-by-side comparison section, in order.
COMPARE_REGIMES = ["retail", "institutional", "exchange"]

RECENT_DAYS = 14             # "recent" window used for shading + recent stats

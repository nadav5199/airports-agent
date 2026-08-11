"""Loads the processed CSVs from data/processed/ once and caches them in memory.

Simple module-level cache (not a database, not re-fetched at query time) -- matches
the "Data storage" decision in CLAUDE.md. Callers should use the module-level
functions below rather than reading CSVs directly, so there's a single place that
knows the on-disk layout.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

# repo_root/scoring/data_loader.py -> repo_root
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "processed"


def _read_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Expected processed data file at {path}. Run ingestion/run_all.py first."
        )
    return pd.read_csv(path)


@lru_cache(maxsize=1)
def load_airports() -> pd.DataFrame:
    return _read_csv("airports.csv")


@lru_cache(maxsize=1)
def load_operations() -> pd.DataFrame:
    return _read_csv("operations.csv")


@lru_cache(maxsize=1)
def load_t100_routes() -> pd.DataFrame:
    return _read_csv("t100_routes.csv")


@lru_cache(maxsize=1)
def load_ontime_delays() -> pd.DataFrame:
    return _read_csv("ontime_delays.csv")


@lru_cache(maxsize=1)
def load_capacity_profiles() -> pd.DataFrame:
    return _read_csv("capacity_profiles.csv")


def get_airport_row(airport_code: str) -> pd.Series | None:
    """Return the airports.csv row for airport_code, or None if unknown."""
    airports = load_airports()
    match = airports[airports["airport_code"] == airport_code]
    if match.empty:
        return None
    return match.iloc[0]


def year_month_str(year: int, month: int) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def clear_cache() -> None:
    """Test/dev helper: drop cached frames so a fresh CSV read happens next call."""
    load_airports.cache_clear()
    load_operations.cache_clear()
    load_t100_routes.cache_clear()
    load_ontime_delays.cache_clear()
    load_capacity_profiles.cache_clear()

from __future__ import annotations

import logging
import yfinance as yf
import pandas as pd

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

import config


@dataclass
class GoldData:
    timestamp: datetime
    price: float
    change_1m: float
    ohlcv: dict
    candles: dict[str, pd.DataFrame]   # "1m" | "5m" | "15m" | "1h"
    context: Optional["ContextData"] = None


@dataclass
class ContextData:
    dxy_chg: float = 0.0
    us10y_chg: float = 0.0
    spx_chg: float = 0.0
    btc_chg: float = 0.0
    oil_chg: float = 0.0


# GC=F = COMEX Gold Futures (primary, 23h/day weekdays)
# XAUUSD=X = Spot gold (fallback)
_GOLD_FALLBACKS = ["GC=F", "XAUUSD=X"]

_CORRELATED = {
    "dxy":   "DX-Y.NYB",
    "us10y": "^TNX",
    "spx":   "^GSPC",
    "btc":   "BTC-USD",
    "oil":   "CL=F",
}

_TF_PARAMS = {
    "1m":  {"period": "1d",  "interval": "1m"},
    "5m":  {"period": "5d",  "interval": "5m"},
    "15m": {"period": "5d",  "interval": "15m"},
    "1h":  {"period": "30d", "interval": "1h"},
}

# Ordered preference for deriving current price when 1m is unavailable
_PRICE_TF_PRIORITY = ["1m", "5m", "15m", "1h"]


def _pct_change(df: pd.DataFrame) -> float:
    if df is None or len(df) < 2:
        return 0.0
    prev  = float(df["Close"].iloc[-2])
    curr  = float(df["Close"].iloc[-1])
    return round((curr - prev) / prev * 100, 4) if prev else 0.0


def _fetch_candles(ticker: str) -> dict[str, pd.DataFrame]:
    t = yf.Ticker(ticker)
    result: dict[str, pd.DataFrame] = {}
    for tf, params in _TF_PARAMS.items():
        try:
            df = t.history(**params)
            if df.empty:
                continue
            df.index = df.index.tz_convert("UTC")
            result[tf] = df
        except Exception as e:
            print(f"[fetcher] WARNING: {ticker} {tf} failed — {e}")
    return result


def _best_tf(candles: dict[str, pd.DataFrame]) -> Optional[str]:
    for tf in _PRICE_TF_PRIORITY:
        if tf in candles and len(candles[tf]) >= 2:
            return tf
    return None


def _fetch_candles_with_fallback() -> tuple[str, dict[str, pd.DataFrame]]:
    tickers = [config.GOLD_TICKER] + [t for t in _GOLD_FALLBACKS if t != config.GOLD_TICKER]
    for ticker in tickers:
        candles = _fetch_candles(ticker)
        if _best_tf(candles) is not None:
            if ticker != config.GOLD_TICKER:
                print(f"[fetcher] INFO: using fallback ticker {ticker}")
            return ticker, candles
    return config.GOLD_TICKER, {}


def _fetch_context() -> ContextData:
    chg: dict[str, float] = {}
    for key, ticker in _CORRELATED.items():
        try:
            df = yf.Ticker(ticker).history(period="1d", interval="5m")
            chg[f"{key}_chg"] = _pct_change(df) if not df.empty else 0.0
        except Exception as e:
            print(f"[fetcher] WARNING: context {ticker} failed — {e}")
            chg[f"{key}_chg"] = 0.0
    return ContextData(**chg)


def fetch_all() -> Optional[GoldData]:
    ticker, candles = _fetch_candles_with_fallback()

    price_tf = _best_tf(candles)
    if price_tf is None:
        print("[fetcher] ERROR: no data — market may be closed")
        return None

    if price_tf != "1m":
        print(f"[fetcher] INFO: 1m unavailable, using {price_tf} for price/change")

    df_1m    = candles[price_tf]
    last     = df_1m.iloc[-1]
    change   = _pct_change(df_1m)

    context = _fetch_context() if config.ENABLE_MARKET_CONTEXT else None

    return GoldData(
        timestamp = datetime.now(timezone.utc),
        price     = round(float(last["Close"]), 2),
        change_1m = change,
        ohlcv     = {
            "open":   round(float(last["Open"]),   2),
            "high":   round(float(last["High"]),   2),
            "low":    round(float(last["Low"]),    2),
            "close":  round(float(last["Close"]),  2),
            "volume": int(last["Volume"]),
        },
        candles = candles,
        context = context,
    )


if __name__ == "__main__":
    print("[fetcher] Fetching data...")
    data = fetch_all()
    if data:
        dir_symbol = "+" if data.change_1m >= 0 else ""
        print(f"\nXAU/USD  ${data.price:,.2f}  ({dir_symbol}{data.change_1m:.3f}%)")
        print(f"OHLCV    {data.ohlcv}")
        print(f"TFs      {list(data.candles.keys())}")
        if data.context:
            ctx = data.context
            print(f"\nDXY   {ctx.dxy_chg:+.3f}%  |  US10Y {ctx.us10y_chg:+.3f}%")
            print(f"SPX   {ctx.spx_chg:+.3f}%  |  BTC   {ctx.btc_chg:+.3f}%  |  Oil {ctx.oil_chg:+.3f}%")
    else:
        print("[fetcher] ERROR: no data returned")

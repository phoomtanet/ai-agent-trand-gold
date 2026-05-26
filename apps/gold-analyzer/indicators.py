from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional


def _rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    val = (100 - (100 / (1 + rs))).iloc[-1]
    return round(float(val), 2) if not np.isnan(val) else None


def _macd(close: pd.Series) -> dict:
    if len(close) < 26:
        return {"macd_trend": "neutral", "macd_hist": 0.0}
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    hist_val = float(((ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()).iloc[-1])
    if np.isnan(hist_val):
        return {"macd_trend": "neutral", "macd_hist": 0.0}
    trend = "bullish" if hist_val > 0 else ("bearish" if hist_val < 0 else "neutral")
    return {"macd_trend": trend, "macd_hist": round(hist_val, 4)}


def _bb_pct(close: pd.Series, period: int = 20) -> Optional[float]:
    if len(close) < period:
        return None
    ma  = close.rolling(period).mean()
    std = close.rolling(period).std()
    val = ((close - (ma - 2 * std)) / (4 * std)).iloc[-1]
    return round(float(val), 4) if not np.isnan(val) else None


def _ema_trend(close: pd.Series) -> str:
    if len(close) < 50:
        return "neutral"
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    if np.isnan(ema20) or np.isnan(ema50):
        return "neutral"
    return "up" if ema20 > ema50 else "down"


def _atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    if len(df) < period + 1:
        return None
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return round(float(val), 4) if not np.isnan(val) else None


def calculate(candles: dict[str, pd.DataFrame]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for tf, df in candles.items():
        if df is None or df.empty:
            continue
        close = df["Close"]
        ind: dict = {}
        ind["rsi"]      = _rsi(close) or 50.0
        ind.update(_macd(close))
        ind["bb_pct"]   = _bb_pct(close) or 0.5
        ind["ema_trend"] = _ema_trend(close)
        ind["atr"]      = _atr(df) or 0.0
        result[tf] = ind
    return result


if __name__ == "__main__":
    from fetcher import fetch_all

    print("[indicators] Fetching data...")
    data = fetch_all()
    if not data:
        print("[indicators] ERROR: no data from fetcher")
        raise SystemExit(1)

    ind = calculate(data.candles)

    print(f"\n{'TF':<6} {'RSI':>6} {'MACD':>10} {'Hist':>8} {'BB%':>7} {'EMA':>8} {'ATR':>8}")
    print("-" * 60)
    for tf in ["1m", "5m", "15m", "1h"]:
        if tf not in ind:
            print(f"{tf:<6} — no data")
            continue
        i = ind[tf]
        print(
            f"{tf:<6}"
            f" {i['rsi']:>6.1f}"
            f" {i['macd_trend']:>10}"
            f" {i['macd_hist']:>8.4f}"
            f" {i['bb_pct']:>7.3f}"
            f" {i['ema_trend']:>8}"
            f" {i['atr']:>8.2f}"
        )

    nan_found = any(
        v is None or (isinstance(v, float) and np.isnan(v))
        for tf_ind in ind.values()
        for v in tf_ind.values()
    )
    print("\n[indicators] NaN check:", "FAIL — NaN detected" if nan_found else "OK — no NaN")

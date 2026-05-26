from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import yfinance as yf

import config
import storage


def _fetch_price_near(target_time: datetime) -> Optional[float]:
    """ดึงราคาทอง ณ เวลา target_time โดยดึง 1d ล่าสุดแล้วหา candle ที่ใกล้ที่สุด"""
    # ทำให้ timezone-aware เสมอ (MongoDB อาจคืน naive datetime)
    if target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=timezone.utc)

    for ticker in [config.GOLD_TICKER, "XAUUSD=X"]:
        try:
            df = yf.Ticker(ticker).history(period="1d", interval="1m")
            if df.empty:
                continue
            df.index = df.index.tz_convert("UTC")
            secs    = np.array([(t - target_time).total_seconds() for t in df.index])
            closest = int(np.abs(secs).argmin())
            return float(df["Close"].iloc[closest])
        except Exception as e:
            print(f"[outcome_tracker] WARNING: {ticker} failed — {e}")
    return None


def _result_label(correct: bool, change: float) -> str:
    if correct:
        return "ทายถูก"
    if abs(change) < 0.05:
        return "ทายผิด (ราคาแทบไม่ขยับ)"
    return "ทายผิด"


def track_outcomes() -> int:
    """อัพเดต outcome ของ records ที่ผ่านมา 15 นาทีแล้ว — คืนจำนวนที่อัพเดต"""
    now       = datetime.now(timezone.utc)
    cutoff    = now - timedelta(minutes=15)
    untracked = storage.find_untracked(before=cutoff)

    updated = 0
    for rec in untracked:
        record_id = str(rec["_id"])
        entry_price = rec.get("price", 0)
        direction   = (rec.get("analysis") or {}).get("direction", "long")
        target_time = rec["timestamp"] + timedelta(minutes=15)

        actual = _fetch_price_near(target_time)
        if actual is None:
            print(f"[outcome_tracker] SKIP {record_id} — ไม่มีราคา ณ {target_time}")
            continue

        change  = round((actual - entry_price) / entry_price * 100, 4) if entry_price else 0.0
        correct = (
            (direction == "long"  and change > 0) or
            (direction == "short" and change < 0)
        )

        storage.update_outcome(record_id, {
            "price_after_15m":    round(actual, 2),
            "change_after_15m":   change,
            "prediction_correct": correct,
            "result_label":       _result_label(correct, change),
            "tracked_at":         now,
        })
        print(f"[outcome_tracker] Updated {record_id} — {_result_label(correct, change)} ({change:+.4f}%)")
        updated += 1

    return updated


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from fetcher import fetch_all

    storage.connect()

    # ── insert mock record อายุ 20 นาที ──────────────────────────────
    print("[outcome_tracker] Inserting mock record (20 min ago)...")
    data = fetch_all()
    mock_price = data.price if data else 4500.0
    mock_ts    = datetime.now(timezone.utc) - timedelta(minutes=20)

    record_id = storage.save_tick(
        timestamp=mock_ts,
        price=mock_price,
        change_1m=0.05,
        ohlcv={"open": mock_price, "high": mock_price, "low": mock_price,
               "close": mock_price, "volume": 0},
        indicators={"1m": {"rsi": 55.0, "macd_trend": "bullish",
                           "macd_hist": 0.3, "bb_pct": 0.6,
                           "ema_trend": "up", "atr": 2.0}},
        analysis={"direction": "long", "is_safe_entry": True,
                  "safety_score": 7, "confidence": 75},
        status="safe_entry",
    )
    print(f"[outcome_tracker] Inserted _id: {record_id}")

    # ── run tracker ───────────────────────────────────────────────────
    print("\n[outcome_tracker] Running track_outcomes()...")
    n = track_outcomes()
    print(f"[outcome_tracker] Updated {n} record(s)")

    # ── verify ────────────────────────────────────────────────────────
    doc = storage.get_by_id(record_id)
    outcome = doc["outcome"]

    assert outcome["tracked_at"]         is not None, "tracked_at ต้องไม่ None"
    assert outcome["price_after_15m"]    is not None, "price_after_15m ต้องไม่ None"
    assert outcome["result_label"]       is not None, "result_label ต้องไม่ None"
    assert outcome["prediction_correct"] is not None, "prediction_correct ต้องไม่ None"

    print(f"\nOutcome:")
    print(f"  price_after_15m   : {outcome['price_after_15m']}")
    print(f"  change_after_15m  : {outcome['change_after_15m']:+.4f}%")
    print(f"  prediction_correct: {outcome['prediction_correct']}")
    print(f"  result_label      : {outcome['result_label']}")

    # cleanup
    from bson import ObjectId
    storage._col_or_raise().delete_one({"_id": ObjectId(record_id)})
    print("\n[outcome_tracker] Test doc cleaned up")
    print("[outcome_tracker] All checks passed ✓")

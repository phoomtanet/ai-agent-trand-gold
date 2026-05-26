from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from bson import ObjectId

import config

_client: Optional[MongoClient] = None
_col: Optional[Collection] = None


def connect() -> None:
    global _client, _col
    _client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=5000)
    _client.server_info()  # raises if unreachable
    db   = _client[config.MONGODB_DB]
    _col = db["gold_ticks"]
    _create_indexes(_col)
    print(f"[storage] Connected to MongoDB — db: {config.MONGODB_DB}")


def _create_indexes(col: Collection) -> None:
    col.create_index([("timestamp", pymongo.DESCENDING)])
    col.create_index([("status", pymongo.ASCENDING)])
    col.create_index([("outcome.tracked_at", pymongo.ASCENDING)])
    col.create_index([("analysis.safety_score", pymongo.DESCENDING)])
    col.create_index([
        ("market_context.session", pymongo.ASCENDING),
        ("timestamp", pymongo.DESCENDING),
    ])


def _col_or_raise() -> Collection:
    if _col is None:
        raise RuntimeError("storage.connect() must be called first")
    return _col


def save_tick(
    *,
    timestamp: datetime,
    price: float,
    change_1m: float,
    ohlcv: dict,
    indicators: dict,
    market_context: Optional[dict] = None,
    rule_engine: Optional[dict] = None,
    embedding: Optional[list] = None,
    similar_patterns: Optional[list] = None,
    analysis: Optional[dict] = None,
    status: str = "no_trade",
    notified: bool = False,
) -> str:
    doc = {
        "timestamp":      timestamp,
        "price":          price,
        "change_1m":      change_1m,
        "ohlcv_1m":       ohlcv,
        "indicators":     indicators,
        "market_context": market_context or {},
        "rule_engine":    rule_engine or {"passed": False, "failed_reasons": []},
        "embedding":      embedding,
        "similar_patterns": similar_patterns or [],
        "analysis":       analysis,
        "outcome": {
            "price_after_15m":    None,
            "change_after_15m":   None,
            "prediction_correct": None,
            "result_label":       None,
            "tracked_at":         None,
        },
        "notified": notified,
        "status":   status,
    }
    result = _col_or_raise().insert_one(doc)
    return str(result.inserted_id)


def update_outcome(record_id: str, outcome: dict) -> None:
    _col_or_raise().update_one(
        {"_id": ObjectId(record_id)},
        {"$set": {"outcome": outcome}},
    )


def find_untracked(before: datetime) -> list[dict]:
    return list(_col_or_raise().find({
        "outcome.tracked_at": None,
        "timestamp": {"$lt": before},
        "status": "safe_entry",
    }))


def find_recent_with_embeddings(days: int = 7) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return list(_col_or_raise().find(
        {"timestamp": {"$gte": since}, "embedding": {"$ne": None}},
        {"embedding": 1, "analysis.direction": 1, "outcome": 1,
         "timestamp": 1, "market_context.session": 1},
    ))


def get_by_id(record_id: str) -> Optional[dict]:
    return _col_or_raise().find_one({"_id": ObjectId(record_id)})


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    connect()

    # insert test doc
    ts  = datetime.now(timezone.utc)
    rid = save_tick(
        timestamp=ts,
        price=4535.90,
        change_1m=0.026,
        ohlcv={"open": 4534.6, "high": 4539.9, "low": 4534.6, "close": 4535.9, "volume": 0},
        indicators={
            "1m":  {"rsi": 58.3, "macd_trend": "bullish", "macd_hist": 0.30, "bb_pct": 0.68, "ema_trend": "up",   "atr": 3.50},
            "5m":  {"rsi": 55.1, "macd_trend": "bullish", "macd_hist": 0.21, "bb_pct": 0.62, "ema_trend": "up",   "atr": 5.20},
            "15m": {"rsi": 52.0, "macd_trend": "neutral", "macd_hist": 0.01, "bb_pct": 0.55, "ema_trend": "up",   "atr": 12.3},
            "1h":  {"rsi": 48.5, "macd_trend": "bearish", "macd_hist": -0.5, "bb_pct": 0.45, "ema_trend": "down", "atr": 18.7},
        },
        market_context={"session": "US", "risk_sentiment": "neutral", "summary": "test"},
        rule_engine={"passed": True, "failed_reasons": []},
        status="safe_entry",
    )
    print(f"[storage] Inserted _id: {rid}")

    # query back
    doc = get_by_id(rid)
    assert doc is not None, "query failed — document not found"
    assert doc["price"] == 4535.90
    assert doc["status"] == "safe_entry"
    assert doc["outcome"]["tracked_at"] is None
    print(f"[storage] Query OK — price={doc['price']}, status={doc['status']}")

    # update outcome
    update_outcome(rid, {
        "price_after_15m":    4540.0,
        "change_after_15m":   0.09,
        "prediction_correct": True,
        "result_label":       "ทายถูก",
        "tracked_at":         datetime.now(timezone.utc),
    })
    doc2 = get_by_id(rid)
    assert doc2["outcome"]["result_label"] == "ทายถูก"
    print(f"[storage] Outcome update OK — result_label={doc2['outcome']['result_label']}")

    # cleanup test doc
    _col_or_raise().delete_one({"_id": ObjectId(rid)})
    print("[storage] Test doc cleaned up")
    print("\n[storage] All checks passed ✓")

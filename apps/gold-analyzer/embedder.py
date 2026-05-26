from __future__ import annotations

import math
import requests
from typing import Optional

import config
import storage

_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"


# ─── Text Builder ─────────────────────────────────────────────────────────────

def build_text(price: float, change_1m: float, ind: dict, ctx: dict) -> str:
    session = ctx.get("session", "Unknown")
    i1  = ind.get("1m",  {})
    i5  = ind.get("5m",  {})
    i15 = ind.get("15m", {})
    i1h = ind.get("1h",  {})

    return " ".join([
        f"XAU/USD {price:.2f} ({change_1m:+.3f}%). Session: {session}.",
        f"1m RSI {i1.get('rsi', 0):.0f} MACD {i1.get('macd_trend', 'neutral')}"
        f" BB {i1.get('bb_pct', 0)*100:.0f}% ATR {i1.get('atr', 0):.2f}.",
        f"5m RSI {i5.get('rsi', 0):.0f} {i5.get('macd_trend', 'neutral')}.",
        f"15m RSI {i15.get('rsi', 0):.0f} {i15.get('macd_trend', 'neutral')}.",
        f"1h RSI {i1h.get('rsi', 0):.0f} {i1h.get('macd_trend', 'neutral')} bias.",
        f"DXY {ctx.get('dxy_chg', 0):+.2f}% {ctx.get('dxy_impact', 'neutral')}.",
        f"Bond {ctx.get('bond_impact', 'neutral')}.",
        f"SPX {ctx.get('risk_sentiment', 'neutral')}.",
    ])


# ─── Embedding API ────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    resp = requests.post(
        _EMBED_URL,
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": config.EMBEDDING_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


# ─── Similarity ───────────────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0


def find_similar(
    embedding: list[float],
    session: str,
    days: Optional[int] = None,
    top_k: Optional[int] = None,
) -> list[dict]:
    days  = days  or config.EMBEDDING_LOOKBACK_DAYS
    top_k = top_k or config.TOP_K_SIMILAR

    records = storage.find_recent_with_embeddings(days)
    scored: list[dict] = []

    for rec in records:
        rec_emb = rec.get("embedding")
        if not rec_emb:
            continue
        sim = _cosine(embedding, rec_emb)
        # slight boost for same-session matches
        if rec.get("market_context", {}).get("session") == session:
            sim = min(1.0, sim * 1.02)

        ts      = rec.get("timestamp")
        outcome = rec.get("outcome", {})
        analysis = rec.get("analysis", {})
        chg15   = outcome.get("change_after_15m")

        scored.append({
            "timestamp":          ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "similarity":         round(sim, 4),
            "prediction":         analysis.get("direction"),
            "actual_after_15m":   ("bullish" if (chg15 or 0) > 0 else "bearish") if chg15 is not None else None,
            "price_change_15m":   chg15,
            "prediction_correct": outcome.get("prediction_correct"),
            "result_label":       outcome.get("result_label"),
            "pattern_label":      analysis.get("pattern_label"),
        })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]


# ─── Main entry ───────────────────────────────────────────────────────────────

def get_embedding_and_similar(
    price: float,
    change_1m: float,
    ind: dict,
    ctx: dict,
) -> dict:
    text      = build_text(price, change_1m, ind, ctx)
    embedding = get_embedding(text)
    similar   = find_similar(embedding, ctx.get("session", ""))
    return {"text": text, "embedding": embedding, "similar_patterns": similar}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from fetcher import fetch_all
    from indicators import calculate
    from market_context import analyze

    storage.connect()

    print("[embedder] Fetching data...")
    data = fetch_all()
    if not data:
        print("[embedder] ERROR: no data")
        raise SystemExit(1)

    ind = calculate(data.candles)
    ctx = analyze(data.context) if data.context else {}

    text = build_text(data.price, data.change_1m, ind, ctx)
    print(f"\nEmbed text:\n  {text}\n")

    print("[embedder] Calling embedding API...")
    emb = get_embedding(text)
    print(f"Embedding dim : {len(emb)}")
    print(f"Sample values : {emb[:4]}")

    print("\n[embedder] Searching similar patterns...")
    similar = find_similar(emb, ctx.get("session", ""))
    if similar:
        print(f"Top-{len(similar)} similar patterns:")
        for i, p in enumerate(similar, 1):
            label = p.get("result_label") or "ยังไม่มี outcome"
            print(f"  {i}. sim={p['similarity']:.4f} | {p['timestamp']} | {label}")
    else:
        print("  (ยังไม่มี historical embeddings — ปกติถ้าเพิ่งเริ่มรัน)")

    print("\n[embedder] All checks passed ✓")

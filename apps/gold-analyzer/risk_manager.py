from __future__ import annotations

import config


def calculate(price: float, atr: float, direction: str) -> dict:
    sl_dist = atr * 1.2
    tp_dist = atr * 1.5
    rr      = round(tp_dist / sl_dist, 4) if sl_dist else 0.0

    if direction == "long":
        entry_low   = round(price - atr * 0.3, 2)
        entry_high  = round(price + atr * 0.1, 2)
        stop_loss   = round(price - sl_dist,   2)
        take_profit = round(price + tp_dist,   2)
    else:  # short
        entry_low   = round(price - atr * 0.1, 2)
        entry_high  = round(price + atr * 0.3, 2)
        stop_loss   = round(price + sl_dist,   2)
        take_profit = round(price - tp_dist,   2)

    return {
        "entry_low":   entry_low,
        "entry_high":  entry_high,
        "stop_loss":   stop_loss,
        "take_profit": take_profit,
        "sl_pct":      round(sl_dist / price * 100, 4),
        "tp_pct":      round(tp_dist / price * 100, 4),
        "rr_ratio":    rr,
        "valid":       rr >= config.MIN_RR_RATIO,
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from fetcher import fetch_all
    from indicators import calculate as calc_ind

    print("[risk_manager] Fetching data...")
    data = fetch_all()
    if not data:
        print("[risk_manager] ERROR: no data")
        raise SystemExit(1)

    ind = calc_ind(data.candles)
    atr = ind.get("1m", {}).get("atr", 0.0)

    print(f"\nPrice : ${data.price:,.2f}")
    print(f"ATR   : {atr:.4f}")
    print(f"SL    = ATR × 1.2 = {atr * 1.2:.4f}")
    print(f"TP    = ATR × 1.5 = {atr * 1.5:.4f}")

    for direction in ("long", "short"):
        r = calculate(data.price, atr, direction)
        print(f"\n--- {direction.upper()} ---")
        print(f"  Entry     : ${r['entry_low']:,.2f} – ${r['entry_high']:,.2f}")
        print(f"  Stop Loss : ${r['stop_loss']:,.2f}  (-{r['sl_pct']:.3f}%)")
        print(f"  Take Prof : ${r['take_profit']:,.2f}  (+{r['tp_pct']:.3f}%)")
        print(f"  RR Ratio  : {r['rr_ratio']:.2f}  (min={config.MIN_RR_RATIO})  → {'VALID ✓' if r['valid'] else 'INVALID ✗'}")

    # assertions
    r_long  = calculate(data.price, atr, "long")
    r_short = calculate(data.price, atr, "short")
    assert r_long["stop_loss"]   < data.price,      "long SL ต้องต่ำกว่าราคา"
    assert r_long["take_profit"] > data.price,      "long TP ต้องสูงกว่าราคา"
    assert r_short["stop_loss"]  > data.price,      "short SL ต้องสูงกว่าราคา"
    assert r_short["take_profit"] < data.price,     "short TP ต้องต่ำกว่าราคา"
    assert r_long["rr_ratio"]    == r_short["rr_ratio"], "RR ratio ต้องเท่ากันทั้ง 2 ทิศ"
    assert r_long["valid"] == (r_long["rr_ratio"] >= config.MIN_RR_RATIO)

    print("\n[risk_manager] All assertions passed ✓")

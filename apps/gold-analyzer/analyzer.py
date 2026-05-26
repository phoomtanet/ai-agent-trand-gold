from __future__ import annotations

import json
import re
import requests
from typing import Optional

import config

_LLM_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = """คุณเป็น gold trading analyst ที่อนุรักษ์นิยมสูง เน้นความปลอดภัย ไม่เน้นกำไรสูง

กฎบังคับ (ห้ามฝ่าฝืน):
1. ถ้าไม่แน่ใจ → is_safe_entry: false เสมอ
2. safety_score < 6 → is_safe_entry: false เสมอ
3. confidence < 70 → is_safe_entry: false เสมอ
4. MTF ไม่ align (1m vs 15m vs 1h ไม่ชี้ทางเดียวกัน) → ลด safety_score 2 คะแนน
5. market context hostile (DXY > 0.5%) → ลด safety_score 2 คะแนน
6. ห้ามเดาตลาด ห้าม fabricate ข้อมูลที่ไม่มีใน input
7. ตอบเป็น JSON เท่านั้น ห้ามมี text นอก JSON block

Output JSON schema (ห้ามเปลี่ยน key):
{
  "reason_th":      "อธิบายสั้นๆ ว่าทำไม safe หรือไม่ safe (ภาษาไทย 1-3 ประโยค)",
  "mtf_assessment": "ประเมิน multi-timeframe alignment สั้นๆ",
  "direction":      "long" หรือ "short",
  "is_safe_entry":  true หรือ false,
  "entry_low":      ราคาต่ำของ entry zone หรือ null,
  "entry_high":     ราคาสูงของ entry zone หรือ null,
  "stop_loss":      ราคา SL หรือ null,
  "take_profit":    ราคา TP หรือ null,
  "safety_score":   0-10 (int),
  "confidence":     0-100 (int),
  "summary_th":     "สรุป 1 ประโยคสั้นๆ",
  "pattern_label":  "trend_continuation" | "reversal" | "fake_breakout" | "consolidation" | null
}"""

_REQUIRED_FIELDS = [
    "reason_th", "mtf_assessment", "direction", "is_safe_entry",
    "entry_low", "entry_high", "stop_loss", "take_profit",
    "safety_score", "confidence", "summary_th", "pattern_label",
]


def _build_user_message(
    price: float,
    change_1m: float,
    ind: dict,
    ctx: dict,
    similar_patterns: list,
) -> str:
    i1  = ind.get("1m",  {})
    i5  = ind.get("5m",  {})
    i15 = ind.get("15m", {})
    i1h = ind.get("1h",  {})

    lines = [
        "=== ข้อมูลตลาดปัจจุบัน ===",
        f"XAU/USD: ${price:,.2f} ({change_1m:+.3f}%)",
        f"Session: {ctx.get('session', 'Unknown')}",
        "",
        "--- Indicators ---",
        f"1m:  RSI={i1.get('rsi',0):.1f}  MACD={i1.get('macd_trend','?')} (hist={i1.get('macd_hist',0):.3f})"
        f"  BB%={i1.get('bb_pct',0):.2f}  EMA={i1.get('ema_trend','?')}  ATR={i1.get('atr',0):.2f}",
        f"5m:  RSI={i5.get('rsi',0):.1f}  MACD={i5.get('macd_trend','?')} (hist={i5.get('macd_hist',0):.3f})"
        f"  BB%={i5.get('bb_pct',0):.2f}  EMA={i5.get('ema_trend','?')}",
        f"15m: RSI={i15.get('rsi',0):.1f}  MACD={i15.get('macd_trend','?')} (hist={i15.get('macd_hist',0):.3f})"
        f"  BB%={i15.get('bb_pct',0):.2f}  EMA={i15.get('ema_trend','?')}",
        f"1h:  RSI={i1h.get('rsi',0):.1f}  MACD={i1h.get('macd_trend','?')} (hist={i1h.get('macd_hist',0):.3f})"
        f"  BB%={i1h.get('bb_pct',0):.2f}  EMA={i1h.get('ema_trend','?')}",
        "",
        "--- Market Context ---",
        ctx.get("summary", "ไม่มีข้อมูล"),
        f"DXY impact: {ctx.get('dxy_impact','?')} | Bond: {ctx.get('bond_impact','?')} | Sentiment: {ctx.get('risk_sentiment','?')}",
    ]

    if similar_patterns:
        lines += ["", "--- Similar Patterns (historical) ---"]
        for i, p in enumerate(similar_patterns, 1):
            label = p.get("result_label") or "ยังไม่มี outcome"
            chg   = p.get("price_change_15m")
            chg_s = f"{chg:+.2f}%" if chg is not None else "N/A"
            lines.append(
                f"{i}. sim={p.get('similarity',0):.3f} | {p.get('timestamp','')} | "
                f"prediction={p.get('prediction','?')} | actual_15m={chg_s} | {label}"
            )
    else:
        lines += ["", "--- Similar Patterns ---", "ยังไม่มี historical data"]

    lines += ["", "วิเคราะห์และตอบ JSON ตาม schema ที่กำหนด"]
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    # strip markdown code fences if present
    clean = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # find first { ... } block
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(clean)


def _enforce_safety(result: dict) -> dict:
    """Client-side safety net — mirrors system prompt rules."""
    if result.get("safety_score", 0) < config.SAFETY_SCORE_THRESHOLD:
        result["is_safe_entry"] = False
    if result.get("confidence", 0) < config.CONFIDENCE_THRESHOLD:
        result["is_safe_entry"] = False
    if not result.get("is_safe_entry"):
        result["entry_low"]   = None
        result["entry_high"]  = None
        result["stop_loss"]   = None
        result["take_profit"] = None
    return result


def analyze(
    price: float,
    change_1m: float,
    ind: dict,
    ctx: dict,
    similar_patterns: Optional[list] = None,
) -> dict:
    user_msg = _build_user_message(price, change_1m, ind, ctx, similar_patterns or [])

    resp = requests.post(
        _LLM_URL,
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        },
        timeout=60,
    )
    resp.raise_for_status()

    raw = resp.json()["choices"][0]["message"]["content"]
    result = _extract_json(raw)

    # fill missing optional fields with None
    for key in _REQUIRED_FIELDS:
        result.setdefault(key, None)

    return _enforce_safety(result)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from fetcher import fetch_all
    from indicators import calculate
    from market_context import analyze as ctx_analyze

    print("[analyzer] Fetching data...")
    data = fetch_all()
    if not data:
        print("[analyzer] ERROR: no data")
        raise SystemExit(1)

    ind = calculate(data.candles)
    ctx = ctx_analyze(data.context) if data.context else {}

    print("[analyzer] Calling LLM...")
    result = analyze(data.price, data.change_1m, ind, ctx)

    print("\n=== Analysis Result ===")
    for k, v in result.items():
        if k == "reason_th":
            print(f"  reason_th     : {v}")
        elif k == "mtf_assessment":
            print(f"  mtf_assessment: {v}")
        elif k == "summary_th":
            print(f"  summary_th    : {v}")
        else:
            print(f"  {k:<14}: {v}")

    missing = [f for f in _REQUIRED_FIELDS if f not in result]
    if missing:
        print(f"\n[analyzer] FAIL — missing fields: {missing}")
    else:
        print("\n[analyzer] All required fields present ✓")

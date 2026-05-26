from __future__ import annotations

import requests
from datetime import datetime, timezone

import config
import storage

_LLM_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = """คุณเป็นนักวิเคราะห์ทองคำที่อธิบายสภาวะตลาดด้วยภาษาพูดภาษาไทยที่เข้าใจง่าย

กฎการพูด:
1. พูดแบบเป็นธรรมชาติ ไม่เป็นทางการเกินไป เหมือนนักวิเคราะห์พูดในรายการ
2. อธิบาย 3-5 ประโยค ไม่สั้นหรือยาวเกินไป
3. ห้ามแนะนำให้ซื้อหรือขายโดยตรง
4. อธิบาย indicator เป็นภาษาคนทั่วไป เช่น "momentum กำลังขึ้น" แทน "MACD bullish"
5. ระบุ: ราคาปัจจุบัน, ทิศทาง, สาเหตุจากตลาด, สรุปภาพรวม
6. ตอบเป็น plain text ภาษาไทยเท่านั้น ห้าม JSON ห้าม markdown ห้าม bullet points
7. ถ้าตลาดไม่มีทิศทางชัด ให้พูดว่าตลาดยังแกว่งตัวหรือรอทิศทาง อย่าฝืนสรุปว่ามีแนวโน้ม
8. ห้ามมั่นใจเกินจริง — ใช้คำเช่น "ดูเหมือนว่า" "น่าจะ" "รอดูต่อ" แทนการ장단언
9. ถ้า indicator หลาย timeframe ชี้ไปคนละทิศ ห้ามใช้คำว่า "แนวโน้มชัดเจน" ให้บอกว่า "สัญญาณยังขัดแย้งกัน" หรือ "ยังไม่ได้ข้อสรุป"
"""


def _momentum_text(macd_trend: str) -> str:
    return {"bullish": "กำลังขึ้น", "bearish": "กำลังลง"}.get(macd_trend, "ทรงตัว")


def _rsi_text(rsi: float) -> str:
    if rsi >= 70:
        return f"RSI {rsi:.0f} (overbought — ราคาขึ้นมามากแล้ว)"
    if rsi <= 30:
        return f"RSI {rsi:.0f} (oversold — ราคาลงมามากแล้ว)"
    if rsi >= 55:
        return f"RSI {rsi:.0f} (ค่อนข้างแข็ง)"
    if rsi <= 45:
        return f"RSI {rsi:.0f} (ค่อนข้างอ่อน)"
    return f"RSI {rsi:.0f} (กลางๆ)"


def _build_prompt(
    price: float,
    change_1m: float,
    ind: dict,
    ctx: dict,
    history: list[dict],
) -> str:
    i1  = ind.get("1m",  {})
    i5  = ind.get("5m",  {})
    i15 = ind.get("15m", {})
    i1h = ind.get("1h",  {})

    direction = "ขึ้น" if change_1m > 0 else "ลง" if change_1m < 0 else "ทรงตัว"

    lines = [
        f"ราคา XAU/USD ตอนนี้: ${price:,.2f} ({change_1m:+.3f}% — {direction})",
        f"Session: {ctx.get('session', 'Unknown')}",
        "",
        "สัญญาณ indicator:",
        f"- ระยะสั้น (1m): momentum {_momentum_text(i1.get('macd_trend',''))} | {_rsi_text(i1.get('rsi', 50))} | ATR {i1.get('atr', 0):.2f}",
        f"- ระยะกลาง (5m): momentum {_momentum_text(i5.get('macd_trend',''))} | RSI {i5.get('rsi', 50):.0f}",
        f"- ระยะกลาง (15m): momentum {_momentum_text(i15.get('macd_trend',''))} | RSI {i15.get('rsi', 50):.0f}",
        f"- ระยะยาว (1h): momentum {_momentum_text(i1h.get('macd_trend',''))} | RSI {i1h.get('rsi', 50):.0f}",
        "",
        "ตลาดรอบข้าง:",
        f"- Dollar Index: {ctx.get('dxy_chg', 0):+.2f}% ({ctx.get('dxy_impact', 'neutral')})",
        f"- ตลาดหุ้น (SPX): {ctx.get('spx_chg', 0):+.2f}%",
        f"- Risk sentiment: {ctx.get('risk_sentiment', 'neutral')}",
        f"- {ctx.get('summary', '')}",
    ]

    if history:
        lines += ["", "รอบที่ผ่านมา (3 รอบล่าสุด):"]
        for h in history[:3]:
            ts = str(h.get("timestamp", ""))[:16].replace("T", " ")
            price_h = h.get("price", 0)
            chg_h = h.get("change_1m", 0)
            lines.append(f"- {ts} UTC: ${price_h:,.2f} ({chg_h:+.3f}%)")

    lines.append("")
    lines.append("อธิบายสภาวะตลาดตอนนี้ด้วยภาษาพูดภาษาไทยสั้นๆ เป็นธรรมชาติ")
    return "\n".join(lines)


def _fetch_history(limit: int = 5) -> list[dict]:
    try:
        col = storage._db["gold_ticks"]
        docs = list(
            col.find(
                {},
                {"timestamp": 1, "price": 1, "change_1m": 1, "market_context.session": 1},
            )
            .sort("timestamp", -1)
            .limit(limit + 1)
        )
        return docs[1:]  # skip รอบปัจจุบัน (record เพิ่งถูก save ก่อนเรียก)
    except Exception:
        return []


def generate(
    price: float,
    change_1m: float,
    ind: dict,
    ctx: dict,
) -> str:
    history = _fetch_history()
    user_msg = _build_prompt(price, change_1m, ind, ctx, history)

    try:
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
                "temperature": 0.7,
                "max_tokens": 300,
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return text
    except Exception as e:
        print(f"[commentary] ERROR: {e}")
        direction = "ขึ้น" if change_1m > 0 else "ลง" if change_1m < 0 else "ทรงตัว"
        return f"ราคาทองตอนนี้อยู่ที่ ${price:,.2f} ปรับตัว{direction} {abs(change_1m):.3f}% — ไม่สามารถโหลดคำวิเคราะห์ได้ในขณะนี้"


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("[commentary] Connecting to MongoDB...")
    storage.connect()

    print("[commentary] Fetching market data...")
    from fetcher import fetch_all
    from indicators import calculate
    from market_context import analyze as ctx_analyze

    data = fetch_all()
    if not data:
        print("[commentary] ERROR: no data")
        raise SystemExit(1)

    ind = calculate(data.candles)
    ctx = ctx_analyze(data.context) if data.context else {}

    print("[commentary] Calling LLM...")
    text = generate(data.price, data.change_1m, ind, ctx)

    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)
    print("\n[commentary] OK" if text else "\n[commentary] FAIL — empty response")

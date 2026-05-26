from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Optional

import requests

import config


def _esc(text: str) -> str:
    return html.escape(str(text))

_API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"

_TH_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _now_th() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.day} {_TH_MONTHS[now.month]} {now.year} {now.hour:02d}:{now.minute:02d} UTC"


def _send(text: str) -> bool:
    try:
        resp = requests.post(
            _API,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("ok", False)
    except Exception as e:
        print(f"[notifier] ERROR sending Telegram: {e}")
        return False


def send_safe_entry(
    price: float,
    change_1m: float,
    ind: dict,
    ctx: dict,
    analysis: dict,
    risk: dict,
) -> bool:
    i1        = ind.get("1m", {})
    direction = (analysis.get("direction") or "long").capitalize()
    sign      = "+" if change_1m >= 0 else ""

    text = (
        f"<b>XAU/USD — จุดเข้าปลอดภัย ✅</b>\n\n"
        f"ราคา: <b>${price:,.2f}</b> ({sign}{change_1m:.3f}%)\n"
        f"1m RSI: {i1.get('rsi', 0):.0f} | MACD: {i1.get('macd_trend','?').capitalize()} | BB: {i1.get('bb_pct',0)*100:.0f}%\n"
        f"DXY: {ctx.get('dxy_chg',0):+.2f}% | Bond: {ctx.get('bond_impact','?')} | Sentiment: {ctx.get('risk_sentiment','?')}\n"
        f"{_now_th()} ({ctx.get('session','?')} Session)\n\n"
        f"<b>วิเคราะห์:</b>\n"
        f"{analysis.get('reason_th','')}\n\n"
        f"<b>แผนการเทรด ({direction})</b>\n"
        f"เข้า:         ${risk.get('entry_low',0):,.2f} – ${risk.get('entry_high',0):,.2f}\n"
        f"Stop Loss:    ${risk.get('stop_loss',0):,.2f} (-{risk.get('sl_pct',0):.3f}%)  ← ATR×1.2\n"
        f"Take Profit:  ${risk.get('take_profit',0):,.2f} (+{risk.get('tp_pct',0):.3f}%)  ← ATR×1.5\n"
        f"R:R Ratio:    {risk.get('rr_ratio',0):.2f} : 1\n"
        f"Safety: {analysis.get('safety_score',0)}/10 | Confidence: {analysis.get('confidence',0)}%\n\n"
        f"<i>ไม่ใช่คำแนะนำทางการเงิน</i>"
    )
    ok = _send(text)
    if ok:
        print("[notifier] SAFE ENTRY sent ✓")
    return ok


def send_no_trade(
    price: float,
    change_1m: float,
    failed_reasons: list[str],
    ctx: Optional[dict] = None,
) -> bool:
    if not config.NOTIFY_NO_TRADE:
        return False

    sign = "+" if change_1m >= 0 else ""
    reasons_text = "\n".join(f"• {_esc(r)}" for r in failed_reasons) if failed_reasons else "• ไม่ผ่านเงื่อนไข"

    text = (
        f"<b>XAU/USD — ไม่มีจุดเข้าที่ปลอดภัย ⏸</b>\n\n"
        f"ราคา: ${price:,.2f} ({sign}{change_1m:.3f}%)\n"
        f"{_now_th()}\n\n"
        f"<b>เหตุผล:</b>\n"
        f"{reasons_text}\n\n"
        f"รอสัญญาณต่อไป"
    )
    ok = _send(text)
    if ok:
        print("[notifier] NO TRADE sent ✓")
    return ok


def send_error(message: str) -> bool:
    text = f"<b>Gold Analyzer — ERROR ⚠️</b>\n\n{message}\n\n{_now_th()}"
    return _send(text)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from fetcher import fetch_all
    from indicators import calculate
    from market_context import analyze as ctx_analyze
    from risk_manager import calculate as calc_risk

    print("[notifier] Fetching data for test...")
    data = fetch_all()
    if not data:
        print("[notifier] ERROR: no data")
        raise SystemExit(1)

    ind = calculate(data.candles)
    ctx = ctx_analyze(data.context) if data.context else {}
    atr = ind.get("1m", {}).get("atr", 1.0)
    risk = calc_risk(data.price, atr, "long")

    # test NO TRADE (NOTIFY_NO_TRADE ต้องเป็น true)
    original = config.NOTIFY_NO_TRADE
    config.NOTIFY_NO_TRADE = True

    print("\n[notifier] Testing NO TRADE message...")
    ok_no = send_no_trade(
        price=data.price,
        change_1m=data.change_1m,
        failed_reasons=["MACD 1m (bearish) ≠ 5m (bullish) — ไม่ align", "Soft score 2/6 < 3"],
        ctx=ctx,
    )

    # test SAFE ENTRY with mock analysis
    print("\n[notifier] Testing SAFE ENTRY message...")
    mock_analysis = {
        "reason_th":    "MACD ทุก TF align bullish | DXY อ่อนค่าหนุนทอง",
        "direction":    "long",
        "safety_score": 8,
        "confidence":   78,
    }
    ok_safe = send_safe_entry(
        price=data.price,
        change_1m=data.change_1m,
        ind=ind,
        ctx=ctx,
        analysis=mock_analysis,
        risk=risk,
    )

    config.NOTIFY_NO_TRADE = original

    assert ok_no,   "NO TRADE message failed"
    assert ok_safe, "SAFE ENTRY message failed"
    print("\n[notifier] All checks passed ✓")

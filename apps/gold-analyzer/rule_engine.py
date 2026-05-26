from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuleResult:
    passed: bool
    soft_score: int
    failed_reasons: list[str]       = field(default_factory=list)
    soft_reasons:   list[str]       = field(default_factory=list)
    hard_rules:     list[dict]      = field(default_factory=list)


# ─── Hard Rules ───────────────────────────────────────────────────────────────

def _macd_1m_5m_aligned(ind: dict) -> tuple[bool, str]:
    t1 = ind.get("1m", {}).get("macd_trend", "neutral")
    t5 = ind.get("5m", {}).get("macd_trend", "neutral")
    if t1 == t5 and t1 != "neutral":
        return True, f"MACD 1m+5m aligned ({t1})"
    return False, f"MACD 1m ({t1}) ≠ 5m ({t5}) — ไม่ align"


def _rsi_not_extreme(ind: dict, low: float = 28, high: float = 75) -> tuple[bool, str]:
    rsi = ind.get("1m", {}).get("rsi", 50.0)
    if low <= rsi <= high:
        return True, f"RSI 1m {rsi:.1f} อยู่ในช่วงปกติ ({low}-{high})"
    side = "overbought" if rsi > high else "oversold"
    return False, f"RSI 1m {rsi:.1f} — {side} (ต้องอยู่ใน {low}-{high})"


def _atr_not_spiked(ind: dict, multiplier: float = 2.5) -> tuple[bool, str]:
    atr_1m  = ind.get("1m",  {}).get("atr", 0.0)
    atr_15m = ind.get("15m", {}).get("atr", 0.0)
    if atr_15m <= 0:
        return True, "ATR baseline ไม่มีข้อมูล — ข้ามการตรวจ"
    threshold = atr_15m * multiplier
    if atr_1m <= threshold:
        return True, f"ATR 1m {atr_1m:.2f} ≤ {threshold:.2f} (15m×{multiplier}) — ไม่ spike"
    return False, f"ATR 1m {atr_1m:.2f} > {threshold:.2f} — ตลาด volatile/panic"


# ─── Soft Scores ──────────────────────────────────────────────────────────────

def _mtf_15m_aligned(ind: dict) -> tuple[int, str]:
    t1  = ind.get("1m",  {}).get("macd_trend", "neutral")
    t15 = ind.get("15m", {}).get("macd_trend", "neutral")
    if t1 == t15 and t1 != "neutral":
        return 2, f"+2 MACD 1m+15m aligned ({t1})"
    return 0, f"MACD 1m ({t1}) ≠ 15m ({t15})"


def _mtf_1h_aligned(ind: dict) -> tuple[int, str]:
    t1 = ind.get("1m", {}).get("macd_trend", "neutral")
    t1h = ind.get("1h", {}).get("macd_trend", "neutral")
    if t1 == t1h and t1 != "neutral":
        return 1, f"+1 MACD 1m+1h aligned ({t1})"
    return 0, f"MACD 1m ({t1}) ≠ 1h ({t1h})"


def _rsi_sweet_spot(ind: dict, low: float = 45, high: float = 62) -> tuple[int, str]:
    rsi = ind.get("1m", {}).get("rsi", 50.0)
    if low <= rsi <= high:
        return 1, f"+1 RSI 1m {rsi:.1f} อยู่ใน sweet spot ({low}-{high})"
    return 0, f"RSI 1m {rsi:.1f} นอก sweet spot ({low}-{high})"


def _bb_not_extreme(ind: dict, low: float = 0.15, high: float = 0.85) -> tuple[int, str]:
    bb = ind.get("1m", {}).get("bb_pct", 0.5)
    if low <= bb <= high:
        return 1, f"+1 BB% 1m {bb:.2f} ไม่อยู่ที่ขอบ band"
    return 0, f"BB% 1m {bb:.2f} ชิดขอบ band (ต้องอยู่ใน {low}-{high})"


def _context_friendly(market_ctx: dict) -> tuple[int, str]:
    dxy = abs(market_ctx.get("dxy_chg", 0.0))
    if dxy <= 0.5:
        return 1, f"+1 DXY change {dxy:.2f}% ≤ 0.5% — ไม่วิ่งแรง"
    return 0, f"DXY change {dxy:.2f}% > 0.5% — Dollar วิ่งแรง กดดันทอง"


# ─── Main ─────────────────────────────────────────────────────────────────────

def check(ind: dict, market_ctx: dict | None = None) -> RuleResult:
    ctx = market_ctx or {}

    # Hard Rules — ต้องผ่านทั้งหมด
    hard_check_results = [
        ("MACD 1m+5m aligned", *_macd_1m_5m_aligned(ind)),
        ("RSI not extreme",    *_rsi_not_extreme(ind)),
        ("ATR not spiked",     *_atr_not_spiked(ind)),
    ]
    hard_rules = [{"name": name, "passed": ok, "detail": msg} for name, ok, msg in hard_check_results]
    failed_reasons = [msg for _, ok, msg in hard_check_results if not ok]
    if failed_reasons:
        return RuleResult(passed=False, soft_score=0, failed_reasons=failed_reasons, hard_rules=hard_rules)

    # Soft Score — ต้องได้ >= 3 (max 6)
    soft_checks = [
        _mtf_15m_aligned(ind),
        _mtf_1h_aligned(ind),
        _rsi_sweet_spot(ind),
        _bb_not_extreme(ind),
        _context_friendly(ctx),
    ]
    soft_score   = sum(score for score, _ in soft_checks)
    soft_reasons = [msg for _, msg in soft_checks]

    passed = soft_score >= 3
    if not passed:
        failed_reasons = [f"Soft score {soft_score}/6 < 3 — สัญญาณไม่แข็งแกร่งพอ"]

    return RuleResult(
        passed=passed,
        soft_score=soft_score,
        failed_reasons=failed_reasons,
        soft_reasons=soft_reasons,
        hard_rules=hard_rules,
    )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from fetcher import fetch_all
    from indicators import calculate
    from market_context import analyze

    print("[rule_engine] Fetching data...")
    data = fetch_all()
    if not data:
        print("[rule_engine] ERROR: no data")
        raise SystemExit(1)

    ind = calculate(data.candles)
    ctx = analyze(data.context) if data.context else {}
    result = check(ind, ctx)

    print(f"\n{'='*50}")
    verdict = "PASS — ส่งต่อ AI" if result.passed else "BLOCK — NO TRADE"
    print(f"Rule Engine : {verdict}")
    print(f"Soft Score  : {result.soft_score}/6")

    if result.failed_reasons:
        print("\nFailed:")
        for r in result.failed_reasons:
            print(f"  ✗ {r}")

    print("\nSoft breakdown:")
    for r in result.soft_reasons:
        print(f"  {'✓' if r.startswith('+') else '–'} {r}")
    print(f"{'='*50}")

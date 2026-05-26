from __future__ import annotations

import sys
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

import config
import storage
import fetcher
import indicators
import market_context
import rule_engine
import embedder
import analyzer
import risk_manager
import notifier
import outcome_tracker

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _validate_startup() -> None:
    print("[main] ── Startup Validation ────────────────────────")

    # 1. env vars
    config.validate()
    print("[main] ✓ env vars")

    # 2. MongoDB
    storage.connect()
    print("[main] ✓ MongoDB")

    # 3. OpenRouter embedding
    test_emb = embedder.get_embedding("gold test")
    assert len(test_emb) > 0, "embedding empty"
    print(f"[main] ✓ OpenRouter embedding (dim={len(test_emb)})")

    # 4. Telegram
    ok = notifier.send_error("Gold Analyzer started ✅")
    assert ok, "Telegram send failed"
    print("[main] ✓ Telegram")

    print("[main] ── All checks passed — starting scheduler ────")


def _log_cycle(
    data: fetcher.GoldData,
    ind: dict,
    ctx: dict,
    rule: rule_engine.RuleResult,
    analysis: dict | None = None,
    risk: dict | None = None,
) -> None:
    i1   = ind.get("1m", {})
    sign = "+" if data.change_1m >= 0 else ""
    verdict = "PASS" if rule.passed else "BLOCK"

    print(
        f"[{_ts()}] ${data.price:,.2f} ({sign}{data.change_1m:.3f}%) | "
        f"RSI={i1.get('rsi',0):.0f} MACD={i1.get('macd_trend','?')} | "
        f"Session={ctx.get('session','?')} | Rule={verdict} score={rule.soft_score}/6"
        , end=""
    )

    if analysis:
        safe = "✅ SAFE" if analysis.get("is_safe_entry") else "⛔ NO"
        print(
            f" | AI={safe} safety={analysis.get('safety_score',0)}"
            f" conf={analysis.get('confidence',0)}%"
            , end=""
        )
    print()


def run_cycle() -> None:
    try:
        # ── Fetch ──────────────────────────────────────────────────────
        data = fetcher.fetch_all()
        if not data:
            print(f"[{_ts()}] SKIP — no market data")
            return

        # ── Indicators + Context ────────────────────────────────────────
        ind = indicators.calculate(data.candles)
        ctx = market_context.analyze(data.context) if data.context else {}

        # ── Rule Engine ─────────────────────────────────────────────────
        rule = rule_engine.check(ind, ctx)

        if not rule.passed:
            _log_cycle(data, ind, ctx, rule)
            storage.save_tick(
                timestamp=data.timestamp,
                price=data.price,
                change_1m=data.change_1m,
                ohlcv=data.ohlcv,
                indicators=ind,
                market_context=ctx,
                rule_engine={"passed": False, "failed_reasons": rule.failed_reasons},
                status="no_trade",
            )
            if config.NOTIFY_NO_TRADE:
                notifier.send_no_trade(data.price, data.change_1m, rule.failed_reasons, ctx)
            return

        # ── Embedding + Similar Patterns ────────────────────────────────
        emb_result = embedder.get_embedding_and_similar(
            data.price, data.change_1m, ind, ctx
        )

        # ── LLM Analysis ────────────────────────────────────────────────
        analysis = analyzer.analyze(
            data.price, data.change_1m, ind, ctx,
            emb_result.get("similar_patterns", []),
        )

        # ── Risk Manager ─────────────────────────────────────────────────
        atr      = ind.get("1m", {}).get("atr", 1.0)
        direction = analysis.get("direction", "long")
        risk     = risk_manager.calculate(data.price, atr, direction)

        # override risk levels from LLM if provided
        if analysis.get("entry_low"):  risk["entry_low"]   = analysis["entry_low"]
        if analysis.get("entry_high"): risk["entry_high"]  = analysis["entry_high"]
        if analysis.get("stop_loss"):  risk["stop_loss"]   = analysis["stop_loss"]
        if analysis.get("take_profit"): risk["take_profit"] = analysis["take_profit"]

        _log_cycle(data, ind, ctx, rule, analysis, risk)

        status = "safe_entry" if analysis.get("is_safe_entry") else "no_signal"
        storage.save_tick(
            timestamp=data.timestamp,
            price=data.price,
            change_1m=data.change_1m,
            ohlcv=data.ohlcv,
            indicators=ind,
            market_context=ctx,
            rule_engine={"passed": True, "failed_reasons": []},
            embedding=emb_result.get("embedding"),
            similar_patterns=emb_result.get("similar_patterns", []),
            analysis=analysis,
            status=status,
        )

        if analysis.get("is_safe_entry") and risk.get("valid"):
            notifier.send_safe_entry(data.price, data.change_1m, ind, ctx, analysis, risk)

    except Exception as e:
        print(f"[{_ts()}] ERROR in run_cycle: {e}")
        notifier.send_error(f"run_cycle error: {e}")


def _track_outcomes_job() -> None:
    try:
        n = outcome_tracker.track_outcomes()
        if n:
            print(f"[{_ts()}] outcome_tracker: updated {n} record(s)")
    except Exception as e:
        print(f"[{_ts()}] ERROR in track_outcomes: {e}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    _validate_startup()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_cycle,           "interval", seconds=config.FETCH_INTERVAL_SEC, id="run_cycle",   next_run_time=datetime.now(timezone.utc))
    scheduler.add_job(_track_outcomes_job, "interval", seconds=300,                        id="track_outcomes")

    print(f"[main] Scheduler started — run_cycle every {config.FETCH_INTERVAL_SEC}s, track_outcomes every 300s")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[main] Stopped.")

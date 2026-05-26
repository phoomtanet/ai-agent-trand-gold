from __future__ import annotations

from datetime import datetime, timezone
from fetcher import ContextData


def get_session() -> str:
    hour = datetime.now(timezone.utc).hour
    if 7 <= hour < 13:
        return "European"
    if 13 <= hour < 22:
        return "US"
    return "Asian"  # 22-23 + 00-06


def _dxy_impact(chg: float) -> tuple[str, str]:
    if chg > 0.2:
        return "negative", f"Dollar แข็งค่า {chg:+.2f}% กดดันทอง"
    if chg < -0.2:
        return "positive", f"Dollar อ่อนค่า {chg:+.2f}% หนุนทอง"
    return "neutral", "Dollar ทรงตัว"


def _bond_impact(chg: float) -> tuple[str, str]:
    if chg > 0.01:
        return "negative", f"Bond Yield สูงขึ้น {chg:+.3f}% กดดันทอง"
    if chg < -0.01:
        return "positive", f"Bond Yield ลดลง {chg:+.3f}% หนุนทอง"
    return "neutral", "Bond Yield ทรงตัว"


def _risk_sentiment(spx_chg: float, btc_chg: float) -> tuple[str, str]:
    if spx_chg < -0.5:
        return "risk_off", f"SPX {spx_chg:+.2f}% (risk-off หนุนทอง)"
    if spx_chg > 0.5:
        return "risk_on", f"SPX {spx_chg:+.2f}% (risk-on กดดันทอง)"
    if btc_chg > 2.0:
        return "risk_on", f"BTC {btc_chg:+.2f}% (risk appetite สูง)"
    if btc_chg < -2.0:
        return "risk_off", f"BTC {btc_chg:+.2f}% (risk-off)"
    return "neutral", f"SPX {spx_chg:+.2f}% ทรงตัว"


def _oil_note(oil_chg: float) -> str | None:
    if oil_chg > 0.5:
        return f"Oil {oil_chg:+.2f}% (inflation proxy หนุนทอง)"
    if oil_chg < -0.5:
        return f"Oil {oil_chg:+.2f}% (deflation signal)"
    return None


def analyze(ctx: ContextData) -> dict:
    dxy_impact,  dxy_text  = _dxy_impact(ctx.dxy_chg)
    bond_impact, bond_text = _bond_impact(ctx.us10y_chg)
    risk_sentiment, risk_text = _risk_sentiment(ctx.spx_chg, ctx.btc_chg)

    parts = [dxy_text, bond_text, risk_text]
    oil_note = _oil_note(ctx.oil_chg)
    if oil_note:
        parts.append(oil_note)
    summary = " | ".join(parts)

    return {
        "dxy_chg":        ctx.dxy_chg,
        "us10y_chg":      ctx.us10y_chg,
        "spx_chg":        ctx.spx_chg,
        "btc_chg":        ctx.btc_chg,
        "oil_chg":        ctx.oil_chg,
        "dxy_impact":     dxy_impact,
        "bond_impact":    bond_impact,
        "risk_sentiment": risk_sentiment,
        "session":        get_session(),
        "summary":        summary,
    }


if __name__ == "__main__":
    from fetcher import fetch_all

    print("[market_context] Fetching data...")
    data = fetch_all()
    if not data or not data.context:
        print("[market_context] ERROR: no context data")
        raise SystemExit(1)

    result = analyze(data.context)

    print(f"\nSession   : {result['session']}")
    print(f"DXY       : {result['dxy_chg']:+.3f}%  → {result['dxy_impact']}")
    print(f"US10Y     : {result['us10y_chg']:+.3f}%  → {result['bond_impact']}")
    print(f"Sentiment : {result['risk_sentiment']}")
    print(f"\nSummary   : {result['summary']}")

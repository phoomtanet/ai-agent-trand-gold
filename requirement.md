# Gold Analyzer — Requirement Document

## ภาพรวมระบบ (Overview)

ระบบวิเคราะห์ราคาทอง XAU/USD แบบ Real-time เพื่อ **หาจุดเข้าที่ปลอดภัย** (ไม่ใช่ระบบเทรดอัตโนมัติ)
ดึงราคาทุก 1 นาที ผ่าน Pipeline 8 ขั้นตอน แจ้งเตือนผ่าน Telegram เฉพาะเมื่อสภาวะตลาดปลอดภัยเพียงพอ

> **สำคัญ:** AI วิเคราะห์จุดเข้า — ไม่ได้เทรดแทนมนุษย์

---

## เป้าหมายหลัก

1. **ติดตามราคา** — XAU/USD + Correlated Assets ทุก 1 นาที
2. **Multi-timeframe** — วิเคราะห์ 1m / 5m / 15m / 1h พร้อมกัน ไม่ดูแค่ 1m เดียว
3. **Market Context จริง** — รู้ว่า DXY แข็ง / Bond Yield สูง / SPX แดง → AI อธิบายได้ว่าทำไม
4. **Rule Engine กรองก่อน** — AI ถูกเรียกเฉพาะเมื่อผ่าน pre-conditions → ไม่มั่วใน noise
5. **Dynamic Risk** — SL/TP ปรับตาม ATR ไม่ static
6. **Outcome Tracking** — ติดตามว่า AI แม่นแค่ไหน เพื่อปรับ confidence ในอนาคต

---

## Architecture

```
[Fetcher]
    |  XAU/USD candles: 1m, 5m, 15m, 1h
    |  Correlated: DXY, US10Y, SPX, BTC, Oil (1m latest)
    v
[Indicators]
    |  RSI, MACD, BB, EMA, ATR — แต่ละ timeframe แยกกัน
    v
[Market Context]
    |  DXY %, US10Y direction, SPX bias, BTC, Oil
    |  Session: Asian / European / US
    |  summary text สำหรับ AI
    v
[Rule Engine]  <- กรองก่อน ถ้าไม่ผ่าน Hard Rules -> NO TRADE ทันที (ไม่เรียก AI)
    |  Hard Rules (ต้องผ่านทั้งหมด): 1m+5m MACD align, RSI 28-75, ATR ไม่ spike
    |  Soft Score (>= 3/5): 15m align, 1h align, RSI sweet spot, BB ok, context ok
    v
[Embedding Similarity]
    |  encode market state -> cosine similarity
    |  กับ 7-30 วันในอดีต พร้อม actual outcome
    |  -> top-3 similar patterns
    v
[LLM Analyzer]
    |  Prompt: state + market context + similar patterns
    |  ถ้าไม่แน่ใจ -> force is_safe_entry: false
    |  Output JSON: reason_th, safety_score, confidence, entry plan
    v
[Risk Manager]
    |  SL = ATR x 1.2  |  TP = ATR x 1.5
    |  RR = TP/SL >= 1.0 -> pass
    |  confidence >= 70% -> pass
    v
[Telegram Notifier]  +  [MongoDB Storage]
    |  SAFE ENTRY alert พร้อม entry/SL/TP
    |  NO TRADE alert (ถ้า NOTIFY_NO_TRADE=true)
    v
[Outcome Tracker]  <- job แยก รันหลัง 15 นาที
    |  ดึงราคา actual หลัง 15m
    └  อัพเดต prediction_correct ใน MongoDB
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Gold Price Source | `yfinance GC=F` — ฟรี ไม่ต้อง API key |
| Correlated Assets | `yfinance` — DXY, US10Y, SPX, BTC, Oil |
| Multi-timeframe | `yfinance` — 1m, 5m, 15m, 1h |
| Technical Analysis | `pandas` + `numpy` |
| AI (LLM) | OpenRouter — `google/gemini-2.5-flash-lite` |
| Embedding | OpenRouter — `google/gemini-embedding-2-preview` |
| Database | MongoDB |
| Notification | Telegram Bot API (HTTP) |
| Scheduler | `APScheduler` |
| Runtime | Python 3.12 / Docker |

---

## Modules

### 1. `fetcher.py` — Multi-asset Data

**Gold (Primary)**
- Ticker: `GC=F` (COMEX Gold Futures)
- Fetch: 1m (2h), 5m (1d), 15m (5d), 1h (30d)
- คำนวณ `change_1m` % เทียบ candle ก่อนหน้า

**Correlated Assets** (เมื่อ `ENABLE_MARKET_CONTEXT=true`)

| Asset | Ticker | ผลต่อทอง |
|---|---|---|
| Dollar Index | `DX-Y.NYB` | DXY up -> Gold down (inverse) |
| US 10Y Bond | `^TNX` | Yield up -> Gold down (opportunity cost) |
| S&P 500 | `^GSPC` | SPX down -> Risk-off -> Gold up |
| Bitcoin | `BTC-USD` | ดู risk appetite ตลาด |
| Crude Oil | `CL=F` | Inflation proxy |

Return structure:
```python
{
    "gold": { "1m": df_1m, "5m": df_5m, "15m": df_15m, "1h": df_1h },
    "context": {
        "dxy_chg": 0.4, "us10y_chg": 0.02,
        "spx_chg": -0.3, "btc_chg": 1.5, "oil_chg": 0.8
    }
}
```

---

### 2. `indicators.py` — Multi-timeframe

คำนวณ indicators ทุก timeframe แยกกัน:

| Indicator | Param | หน้าที่ |
|---|---|---|
| RSI | 14 | overbought/oversold |
| MACD | 12/26/9 | momentum + direction |
| Bollinger Bands | 20, ±2sigma | volatility + price position |
| EMA | 20, 50 | trend direction |
| ATR | 14 | volatility — ใช้ sizing SL/TP |

Output structure:
```python
{
    "1m":  { "rsi": 58.3, "macd_trend": "bullish", "macd_hist": 0.30,
             "bb_pct": 0.68, "ema_trend": "up", "atr": 3.50 },
    "5m":  { "rsi": 55.1, "macd_trend": "bullish", "bb_pct": 0.62, "ema_trend": "up" },
    "15m": { "rsi": 52.0, "macd_trend": "neutral", "bb_pct": 0.55, "ema_trend": "up" },
    "1h":  { "rsi": 48.5, "macd_trend": "bearish", "bb_pct": 0.45, "ema_trend": "down" }
}
```

**MTF Confluence Logic:**
```
1m + 5m + 15m bullish -> strong signal -> Rule Engine pass
1m bullish, 15m bearish -> bounce only -> Rule Engine block
```

---

### 3. `market_context.py` — Correlated Assets Analysis

```python
def get_market_bias(context: dict) -> dict:
    return {
        "dxy_impact":     "negative" if context["dxy_chg"] > 0.2 else "neutral",
        "bond_impact":    "negative" if context["us10y_chg"] > 0.01 else "neutral",
        "risk_sentiment": "risk_off" if context["spx_chg"] < -0.5 else "risk_on",
        "session":        get_session(),  # "Asian" | "European" | "US"
        "summary":        "DXY +0.4% กดดันทอง | Bond Yield สูงขึ้น | SPX แดง (risk-off)"
    }
```

`summary` ใส่ใน AI prompt เพื่อให้ AI อธิบายได้ว่า "ทองลงเพราะ Dollar แข็งค่า" แทนที่จะตอบ generic

---

### 4. `rule_engine.py` — Pre-filter ก่อนเรียก AI

แบ่งเป็น **Hard Rules** (บล็อกทันที) + **Soft Score** (คะแนนรวม):

```python
# Hard Rules — ต้องผ่านทั้งหมด ถ้าไม่ผ่านข้อใดข้อหนึ่ง = NO TRADE ทันที
hard_rules = [
    macd_1m_5m_aligned(ind),                     # 1m + 5m MACD ชี้ทางเดียวกัน (สำคัญที่สุด)
    rsi_not_extreme(ind["1m"]["rsi"], 28, 75),    # ป้องกัน chase extreme
    atr_not_spiked(ind["1m"]["atr"], multiplier=2.5),  # ตลาดไม่ panic
]

# Soft Scores — ยิ่งมากยิ่งดี ต้องได้ >= 3/5 จึงส่งต่อ AI
soft_scores = [
    mtf_15m_aligned(ind),        # +2 คะแนน (สำคัญมาก)
    mtf_1h_aligned(ind),         # +1 คะแนน
    rsi_sweet_spot(ind["1m"]["rsi"], 45, 62),  # +1 คะแนน
    bb_not_extreme(ind["1m"]["bb_pct"], 0.15, 0.85),   # +1 คะแนน
    context_friendly(market_bias),  # +1 คะแนน (DXY ไม่วิ่ง > 0.5%)
]
# total max = 6 คะแนน, ต้องได้ >= 3
```

**เป้าหมาย:** Rule Engine ผ่านประมาณ **10-15% ของ ticks** (~140-200 ครั้ง/วัน)
จากนั้น AI กรองเหลือ **3-8 signals/วัน**

**ถ้าไม่ผ่าน:**
- บันทึก MongoDB `status: "no_trade"` พร้อม `failed_reasons`
- ส่ง Telegram NO TRADE (ถ้า `NOTIFY_NO_TRADE=true`)
- ไม่เรียก AI (ประหยัด API cost)

---

### 5. `embedder.py` — Pattern Memory (7–30 วัน)

**Text ที่ embed:**
```
XAU/USD 2350.50 (+0.15%). Session: US.
1m RSI 58 MACD bullish BB 68% ATR 3.50.
5m RSI 55 bullish. 15m RSI 52 neutral. 1h bearish bias.
DXY +0.4% negative. Bond yield rising. SPX red risk-off.
```

**Similarity Search:**
- โหลด embeddings จาก MongoDB: **7 วันล่าสุด** (default), ปรับได้ถึง 30 วัน
- Filter เสริม: `session == current_session` ลด false matches
- Cosine similarity -> **top-3** พร้อม actual outcome

**Outcome ที่แนบกับ pattern (ส่งเป็น context ให้ AI):**
```python
{
    "timestamp": "2026-05-20T10:15:00Z",
    "similarity": 0.94,
    "prediction": "bullish",
    "actual_after_15m": "bullish",
    "price_change_15m": +0.28,
    "prediction_correct": True,
    "result_label": "ทายถูก",      # ← AI อ่านได้ตรงๆ ว่าครั้งนั้นถูกหรือผิด
    "pattern_label": "trend_continuation"
}
```

**Pattern Labels** (AI กำหนดเอง):
`"trend_continuation"` | `"reversal"` | `"fake_breakout"` | `"consolidation"` | `null`

---

### 6. `analyzer.py` — LLM Analysis

**System Prompt (บังคับพฤติกรรม):**
```
คุณเป็น gold trading analyst ที่อนุรักษ์นิยมสูง
หลักการ: เน้นความปลอดภัย ไม่เน้นกำไรสูง
กฎบังคับ:
- ถ้าไม่แน่ใจ -> is_safe_entry: false เสมอ
- safety_score < 6 -> is_safe_entry: false เสมอ
- confidence < 70 -> is_safe_entry: false เสมอ
- MTF ไม่ align -> ลด safety_score 2 คะแนน
- market context hostile -> ลด safety_score 2 คะแนน
- ห้ามเดาตลาด ห้าม fabricate ข้อมูล
ตอบเป็น JSON เท่านั้น
```

**Output JSON:**
```json
{
  "reason_th": "ราคาทองลงเพราะ Dollar Index แข็งค่า 0.4%...",
  "mtf_assessment": "1m bullish แต่ 15m และ 1h ยังเป็น bearish",
  "direction": "long",
  "is_safe_entry": false,
  "entry_low": null,
  "entry_high": null,
  "stop_loss": null,
  "take_profit": null,
  "safety_score": 4,
  "confidence": 52,
  "summary_th": "ตลาดไม่เหมาะสมเนื่องจาก MTF ไม่ align และ DXY แข็ง",
  "pattern_label": "fake_breakout"
}
```

---

### 7. `risk_manager.py` — Dynamic Risk

```python
def calculate_risk(price: float, atr: float, direction: str) -> dict:
    sl_dist = atr * 1.2
    tp_dist = atr * 1.5
    rr = tp_dist / sl_dist   # ต้องได้ >= MIN_RR_RATIO

    if direction == "long":
        return {
            "entry_low":   price - atr * 0.3,
            "entry_high":  price + atr * 0.1,
            "stop_loss":   price - sl_dist,
            "take_profit": price + tp_dist,
            "sl_pct":      sl_dist / price * 100,
            "tp_pct":      tp_dist / price * 100,
            "rr_ratio":    rr,
            "valid":       rr >= MIN_RR_RATIO
        }
```

**Filter ก่อนส่ง alert:**
- `rr_ratio < 1.0` -> ยกเลิก (Risk:Reward ไม่คุ้ม)
- `confidence < 70` -> ยกเลิก

---

### 8. `notifier.py` — Telegram Messages

**SAFE ENTRY Alert:**
```
XAU/USD — จุดเข้าปลอดภัย

ราคา: $2,350.50 (+0.15%)
1m RSI: 58 | MACD: Bullish | BB: 68%
DXY: -0.2% | Bond: Stable | SPX: +0.3% (risk-on)
26 พ.ค. 2026 14:30 UTC (US Session)

วิเคราะห์:
ราคาทองปรับตัวขึ้นหลัง Dollar Index อ่อนค่า 0.2%
MACD ทุก timeframe ชี้ขึ้นพร้อมกัน รูปแบบคล้าย
3 ครั้งในอดีตที่ราคาขึ้นต่อเฉลี่ย +0.3%

แผนการเทรด (Long)
เข้า:        $2,348.00 - $2,350.00
Stop Loss:   $2,344.00 (-0.26%) <- ATR x 1.2
Take Profit: $2,355.00 (+0.21%) <- ATR x 1.5
R:R Ratio:   1.5 : 1
Safety:      8/10 | Confidence: 78%

ไม่ใช่คำแนะนำทางการเงิน
```

**NO TRADE Alert** (ส่งเมื่อ `NOTIFY_NO_TRADE=true`):
```
XAU/USD — ไม่มีจุดเข้าที่ปลอดภัย

ราคา: $2,350.50 (-0.22%)
26 พ.ค. 2026 14:30 UTC

เหตุผล:
- 1m bullish แต่ 15m ยังเป็น bearish (MTF ไม่ align)
- DXY +0.4% กดดันราคาทอง
- ATR สูงกว่าปกติ — ตลาด volatile

รอสัญญาณต่อไป
```

**เงื่อนไขการส่ง:**

| Message | เงื่อนไข |
|---|---|
| SAFE ENTRY | `safety_score >= SAFETY_SCORE_THRESHOLD` AND `rr_ratio >= 1.0` AND `confidence >= 60` |
| NO TRADE | Rule Engine ไม่ผ่าน (ถ้า `NOTIFY_NO_TRADE=true`) |
| ERROR | Fetch ล้มเหลว หรือ API error |

> **Warm-up period (2 สัปดาห์แรก):** ตั้ง `SAFETY_SCORE_THRESHOLD=6` ก่อน
> เมื่อมี outcome data สะสมแล้วค่อยปรับเป็น 7 เพื่อเพิ่ม precision

---

### 9. `storage.py` — MongoDB Schema

**Collection: `gold_ticks`**
```json
{
  "_id": "ObjectId",
  "timestamp": "2026-05-26T14:30:00Z",
  "price": 2350.50,
  "change_1m": 0.15,
  "ohlcv_1m": { "open": 2349.0, "high": 2351.0, "low": 2348.5, "close": 2350.5, "volume": 1234 },
  "indicators": {
    "1m":  { "rsi": 58.3, "macd_trend": "bullish", "macd_hist": 0.30, "bb_pct": 0.68, "ema_trend": "up",   "atr": 3.50 },
    "5m":  { "rsi": 55.1, "macd_trend": "bullish", "bb_pct": 0.62, "ema_trend": "up" },
    "15m": { "rsi": 52.0, "macd_trend": "neutral", "bb_pct": 0.55, "ema_trend": "up" },
    "1h":  { "rsi": 48.5, "macd_trend": "bearish", "bb_pct": 0.45, "ema_trend": "down" }
  },
  "market_context": {
    "dxy_chg": -0.20, "us10y_chg": 0.005,
    "spx_chg": 0.30, "btc_chg": 1.2, "oil_chg": 0.5,
    "risk_sentiment": "risk_on",
    "session": "US",
    "summary": "Dollar อ่อนค่า 0.2% หนุนทอง | Bond Yield stable | SPX บวก"
  },
  "rule_engine": {
    "passed": true,
    "failed_reasons": []
  },
  "embedding": [0.021, -0.043, "...3072 dims"],
  "similar_patterns": [
    {
      "timestamp": "2026-05-20T10:15:00Z",
      "similarity": 0.94,
      "prediction": "bullish",
      "actual_after_15m": "bullish",
      "price_change_15m": 0.28,
      "prediction_correct": true,
      "pattern_label": "trend_continuation"
    }
  ],
  "analysis": {
    "reason_th": "ราคาทองปรับตัวขึ้น...",
    "mtf_assessment": "1m 5m 15m align bullish...",
    "direction": "long",
    "is_safe_entry": true,
    "entry_low": 2348.0,  "entry_high": 2350.0,
    "stop_loss": 2344.0,  "take_profit": 2355.0,
    "sl_pct": 0.26,       "tp_pct": 0.21,
    "rr_ratio": 1.5,
    "safety_score": 8,
    "confidence": 78,
    "summary_th": "สรุปสั้นๆ",
    "pattern_label": "trend_continuation"
  },
  "outcome": {
    "price_after_15m": null,
    "change_after_15m": null,
    "prediction_correct": null,
    "result_label": null,
    "tracked_at": null
  },
  "notified": false,
  "status": "safe_entry"
}
```

**MongoDB Indexes:**
```js
{ "timestamp": -1 }
{ "status": 1 }
{ "outcome.tracked_at": 1 }
{ "analysis.safety_score": -1 }
{ "market_context.session": 1, "timestamp": -1 }
```

---

### 10. `outcome_tracker.py` — Learning Loop

Job แยก รันทุก 5 นาที — อัพเดต records ที่ผ่านมา 15 นาทีแล้ว:

```python
untracked = db.gold_ticks.find({
    "outcome.tracked_at": None,
    "timestamp": { "$lt": now - timedelta(minutes=15) },
    "status": "safe_entry"
})

for record in untracked:
    actual = fetch_price_near(record["timestamp"] + timedelta(minutes=15))
    change = (actual - record["price"]) / record["price"] * 100
    correct = (
        (record["analysis"]["direction"] == "long" and change > 0) or
        (record["analysis"]["direction"] == "short" and change < 0)
    )
    if correct:
        label = "ทายถูก"
    elif abs(change) < 0.05:
        label = "ทายผิด (ราคาแทบไม่ขยับ)"
    else:
        label = "ทายผิด"

    db.update(record["_id"], outcome={
        "price_after_15m": actual,
        "change_after_15m": change,
        "prediction_correct": correct,
        "result_label": label,
        "tracked_at": now
    })
```

ข้อมูลนี้ feed กลับเป็น context ใน similar patterns -> AI แม่นขึ้นเรื่อยๆ

---

### 11. `main.py` — Scheduler

```
startup:
  1. validate all env vars
  2. test MongoDB connection
  3. test OpenRouter API (embedding + LLM)
  4. test Telegram -> send "Gold Analyzer started"
  5. APScheduler:
     - run_cycle()       ทุก 60 วินาที
     - track_outcomes()  ทุก 5 นาที

run_cycle():
  data     = fetcher.fetch_all()
  ind      = indicators.calculate(data.gold)
  ctx      = market_context.analyze(data.context)
  rule     = rule_engine.check(ind, ctx)
  if not rule.passed:
      storage.save(status="no_trade", failed_reasons=rule.failed_reasons)
      if NOTIFY_NO_TRADE: notifier.send_no_trade(rule.failed_reasons)
      return
  emb      = embedder.get_embedding_and_similar(ind, ctx)
  analysis = analyzer.analyze(data, ind, ctx, emb)
  risk     = risk_manager.calculate(data.price, ind["1m"]["atr"], analysis.direction)
  storage.save(status="safe_entry" if analysis.is_safe_entry else "no_signal")
  log_to_console(data, ind, ctx, analysis, risk)
  if analysis.is_safe_entry and risk.valid:
      notifier.send_safe_entry(data, ind, ctx, analysis, risk)
```

---

## Environment Variables

```env
# OpenRouter
OPENROUTER_API_KEY=
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
EMBEDDING_MODEL=google/gemini-embedding-2-preview

# MongoDB
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DB=gold_analyzer

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
NOTIFY_NO_TRADE=false

# Market Context
ENABLE_MARKET_CONTEXT=true

# Tuning
GOLD_TICKER=GC=F
FETCH_INTERVAL_SEC=60
SAFETY_SCORE_THRESHOLD=6   # warm-up: 6, stable: 7
CONFIDENCE_THRESHOLD=60    # warm-up: 60, stable: 70
MIN_RR_RATIO=1.0
EMBEDDING_LOOKBACK_DAYS=7
TOP_K_SIMILAR=3
```

---

## Project Structure

```
e:\project\bot-trand\
├── apps\
│   └── gold-analyzer\
│       ├── config.py             # env vars + validation
│       ├── fetcher.py            # yfinance multi-asset, multi-timeframe
│       ├── indicators.py         # RSI, MACD, BB, EMA, ATR (per TF)
│       ├── market_context.py     # DXY/Bond/SPX/BTC/Oil bias + session
│       ├── rule_engine.py        # pre-filter (MTF, RSI, ATR, context)
│       ├── embedder.py           # text embedding + cosine similarity (7-30d)
│       ├── analyzer.py           # OpenRouter LLM + JSON output
│       ├── risk_manager.py       # ATR-based SL/TP, RR filter
│       ├── notifier.py           # Telegram: SAFE ENTRY + NO TRADE
│       ├── storage.py            # MongoDB CRUD + indexes
│       ├── outcome_tracker.py    # 15m outcome tracking job
│       ├── main.py               # APScheduler entry point
│       ├── requirements.txt
│       └── Dockerfile
├── docker-compose.yml
├── .env
└── .env.example
```

---

## Phases

### Phase 1 — Core Data Pipeline
- [ ] 1.1 `config.py` — env vars พร้อม validation
- [ ] 1.2 `fetcher.py` — multi-asset + multi-timeframe
- [ ] 1.3 `indicators.py` — RSI, MACD, BB, EMA, ATR ทุก TF
- [ ] 1.4 `market_context.py` — DXY/Bond/SPX/BTC/Oil bias + session
- [ ] 1.5 `storage.py` — MongoDB CRUD + indexes

### Phase 2 — Intelligence Layer
- [ ] 2.1 `rule_engine.py` — pre-filter conditions
- [ ] 2.2 `embedder.py` — embedding + 7-day cosine similarity
- [ ] 2.3 `analyzer.py` — LLM prompt + forced JSON output
- [ ] 2.4 `risk_manager.py` — ATR SL/TP + RR validation

### Phase 3 — Output & Tracking
- [ ] 3.1 `notifier.py` — SAFE ENTRY + NO TRADE messages
- [ ] 3.2 `outcome_tracker.py` — 15m actual outcome job
- [ ] 3.3 `main.py` — scheduler + run_cycle() + startup validation

### Phase 4 — Deploy
- [ ] 4.1 `requirements.txt` + `Dockerfile`
- [ ] 4.2 `docker-compose.yml`
- [ ] 4.3 ทดสอบ end-to-end

---

## Constraints & Decisions

| เรื่อง | การตัดสินใจ | เหตุผล |
|---|---|---|
| Gold source | `yfinance GC=F` | ฟรี ไม่ต้อง key |
| Correlated assets | yfinance (DXY, US10Y, SPX, BTC, Oil) | ให้ AI อธิบาย context ได้จริง |
| Multi-timeframe | 1m / 5m / 15m / 1h | 1m noise มาก ต้องมี higher TF confirm |
| Rule Engine | Python rules ก่อน AI | ลด API cost + ลด hallucination |
| Embedding lookback | 7 วัน (default), ขยาย 30 วัน | session filter ลด false matches |
| SL/TP | ATR x 1.2 / 1.5 | dynamic ตาม volatility จริง |
| RR minimum | 1.0 | ไม่เทรดถ้า reward น้อยกว่า risk |
| Rule Engine | Hard Rules (AND) + Soft Score >= 3/5 | AND ล้วนเข้มเกิน — scoring balance ได้ดีกว่า |
| Alert conditions | score >= 6 (warm-up) / 7 (stable) AND RR >= 1.0 | เริ่ม loose แล้ว tighten เมื่อมี data |
| AI uncertainty | force `is_safe_entry: false` | Gemini ชอบตอบ positive เกินไป |
| NO TRADE alert | optional `NOTIFY_NO_TRADE` | "ไม่เทรด" คือ strategy ที่ดี |
| Outcome tracking | +15m actual price | ใช้ปรับ confidence ระยะยาว |

---

*อัพเดตล่าสุด: 2026-05-26*

# Gold Analyzer — XAU/USD AI Entry Finder



---

## Tech Stack

- **Python 3.12** — gold analyzer service
- **yfinance** — ดึง XAU/USD + DXY/Bond/SPX/BTC/Oil ฟรี
- **pandas + numpy** — RSI, MACD, BB, EMA, ATR
- **OpenRouter API** — LLM (gemini-2.5-flash-lite) + Embedding
- **MongoDB** — เก็บ ticks, embeddings, analysis, outcomes
- **APScheduler** — รัน run_cycle() ทุก 60 วินาที
- **Telegram Bot API** — แจ้ง SAFE ENTRY + NO TRADE
- **Docker** — containerize

---

## Environment Variables

```
OPENROUTER_API_KEY=
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
EMBEDDING_MODEL=google/gemini-embedding-2-preview
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DB=gold_analyzer
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
NOTIFY_NO_TRADE=false
ENABLE_MARKET_CONTEXT=true
GOLD_TICKER=GC=F
FETCH_INTERVAL_SEC=60
SAFETY_SCORE_THRESHOLD=6
CONFIDENCE_THRESHOLD=60
MIN_RR_RATIO=1.0
EMBEDDING_LOOKBACK_DAYS=7
TOP_K_SIMILAR=3
```

---

## Project Structure

```
apps/gold-analyzer/
├── config.py             # env vars + validation
├── fetcher.py            # yfinance multi-asset, multi-timeframe
├── indicators.py         # RSI, MACD, BB, EMA, ATR (per TF)
├── market_context.py     # DXY/Bond/SPX/BTC/Oil bias + session
├── rule_engine.py        # Hard Rules + Soft Score >= 3/5
├── embedder.py           # embedding + cosine similarity (7-30d)
├── analyzer.py           # OpenRouter LLM + JSON output
├── risk_manager.py       # ATR-based SL/TP, RR filter
├── notifier.py           # Telegram: SAFE ENTRY + NO TRADE
├── storage.py            # MongoDB CRUD + indexes
├── outcome_tracker.py    # 15m outcome tracking job
├── main.py               # APScheduler entry point
├── requirements.txt
└── Dockerfile
```

---

## Task Management Rules (สำหรับ AI)

> 1. **เริ่ม task** → เปลี่ยน `[ ]` เป็น `[~]`
> 2. **เจอปัญหา** → เพิ่ม FIX ใต้ task นั้นทันที
> 3. **fix เสร็จ** → `[x]` + เพิ่ม `🧪 test:` และ `📝 commit:` ใต้ FIX item นั้น
> 4. **task เสร็จ** → `[x]` + เพิ่ม `🧪 test:` และ `📝 commit:` ใต้ task หลัก
> 5. **ห้ามลบ** FIX ที่เสร็จแล้ว — เก็บ `[x]` ไว้เป็น history

**สัญลักษณ์:**

| สัญลักษณ์ | ความหมาย |
|---|---|
| `[ ]` | ยังไม่เริ่ม |
| `[~]` | กำลังทำอยู่ |
| `[x]` | เสร็จแล้ว |
| `FIX #N:` | sub-task แก้ปัญหา (สร้างอัตโนมัติ) |
| `before/after:` | แสดงก่อน-หลังแก้ (ถ้าสั้นพอ) |
| `fix:` | สรุปวิธีแก้สั้นๆ (ถ้ายาวเกิน) |
| `🧪 test:` | วิธีทดสอบ + ผลที่ควรเห็น |
| `📝 commit:` | ชื่อ git commit ที่แนะนำ |

**โครงสร้าง:**

```
- [x] 1.1 task หลัก
  - 🧪 test: <คำสั่ง> → <ผลที่ควรเห็น>
  - 📝 commit: `feat(1.1): ...`

  - [x] FIX #1: <ปัญหา> | before: ... → after: ...
    - 🧪 test: <คำสั่ง> → <ผลที่ควรเห็น>
    - 📝 commit: `fix(1.1): ...`
```

---

## Tasks

### Phase 1 — Core Data Pipeline

- [x] 1.1 `config.py` — โหลด env vars + validation ครบทุกตัว
  - 🧪 test: `python config.py` → ไม่มี error, print ค่าทุกตัว ✓
  - 📝 commit: `feat(1.1): add config with env validation`

- [x] 1.2 `fetcher.py` — ดึง XAU/USD 4 timeframes + correlated assets
  - 🧪 test: `python fetcher.py` → print price, change_1m, dxy_chg, spx_chg ✓
  - 📝 commit: `feat(1.2): add multi-asset multi-timeframe fetcher`

  - [x] FIX #1: GC=F ไม่มีข้อมูลวันหยุด US (Memorial Day) | fix: fallback ticker XAUUSD=X + suppress yfinance log

- [x] 1.3 `indicators.py` — RSI, MACD, BB, EMA, ATR ทุก TF
  - 🧪 test: `python indicators.py` → print dict ครบ 4 TF ไม่มี NaN ✓
  - 📝 commit: `feat(1.3): add multi-timeframe technical indicators`

- [ ] 1.4 `market_context.py` — วิเคราะห์ DXY/Bond/SPX/BTC/Oil → summary text
  - 🧪 test: `python market_context.py` → print summary + session + bias
  - 📝 commit: `feat(1.4): add market context analyzer`

- [ ] 1.5 `storage.py` — MongoDB CRUD + สร้าง indexes
  - 🧪 test: `python storage.py` → insert test doc, query กลับมาได้ครบ
  - 📝 commit: `feat(1.5): add mongodb storage with indexes`

---

### Phase 2 — Intelligence Layer

- [ ] 2.1 `rule_engine.py` — Hard Rules (3 ข้อ) + Soft Score (>= 3/5)
  - 🧪 test: `python rule_engine.py` → print passed/failed + score + reasons
  - 📝 commit: `feat(2.1): add rule engine with hard+soft scoring`

- [ ] 2.2 `embedder.py` — text embedding + cosine similarity 7 วัน
  - 🧪 test: `python embedder.py` → print embedding dim + top-3 similar patterns
  - 📝 commit: `feat(2.2): add embedder with cosine similarity search`

- [ ] 2.3 `analyzer.py` — OpenRouter LLM prompt + parse JSON output
  - 🧪 test: `python analyzer.py` → print analysis JSON ครบทุก field
  - 📝 commit: `feat(2.3): add llm analyzer with structured json output`

- [ ] 2.4 `risk_manager.py` — ATR × 1.2/1.5 SL/TP + RR validation
  - 🧪 test: `python risk_manager.py` → print entry/SL/TP/RR ถูกต้อง
  - 📝 commit: `feat(2.4): add atr-based risk manager`

---

### Phase 3 — Output & Tracking

- [ ] 3.1 `notifier.py` — Telegram SAFE ENTRY + NO TRADE messages
  - 🧪 test: `python notifier.py` → ข้อความถูกส่งใน Telegram จริง
  - 📝 commit: `feat(3.1): add telegram notifier with safe entry and no trade`

- [ ] 3.2 `outcome_tracker.py` — อัพเดต prediction_correct + result_label ("ทายถูก"/"ทายผิด") หลัง 15 นาที
  - 🧪 test: insert mock record อายุ > 15m → tracker อัพเดต outcome + result_label ได้
  - 📝 commit: `feat(3.2): add 15m outcome tracker with result_label`

- [ ] 3.3 `main.py` — startup validation + APScheduler run_cycle() ทุก 60s
  - 🧪 test: `python main.py` → เห็น log ทุก 60 วินาที ไม่ crash
  - 📝 commit: `feat(3.3): add main scheduler with startup validation`

---

### Phase 4 — Deploy

- [ ] 4.1 `requirements.txt` + `Dockerfile`
  - 🧪 test: `docker build -t gold-analyzer .` → build สำเร็จ ไม่มี error
  - 📝 commit: `feat(4.1): add dockerfile and requirements`

- [ ] 4.2 `docker-compose.yml` — gold-analyzer + mongodb services
  - 🧪 test: `docker-compose up` → ทั้งสอง service up, log ปกติ
  - 📝 commit: `feat(4.2): add docker-compose with mongodb`

- [ ] 4.3 ทดสอบ end-to-end
  - 🧪 test: รัน 5 นาที → เห็น log ทุก 1 นาที, มี record ใน MongoDB, ถ้า signal → Telegram ส่งจริง
  - 📝 commit: `feat(4.3): verified end-to-end pipeline`
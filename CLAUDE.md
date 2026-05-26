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


เสร็จแล้วให้เทส ถ้าผ่านให้ x แก้จนผ่านค่อย x

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

- [x] 1.4 `market_context.py` — วิเคราะห์ DXY/Bond/SPX/BTC/Oil → summary text
  - 🧪 test: `python market_context.py` → print summary + session + bias ✓
  - 📝 commit: `feat(1.4): add market context analyzer`

- [x] 1.5 `storage.py` — MongoDB CRUD + สร้าง indexes
  - 🧪 test: `python storage.py` → insert test doc, query กลับมาได้ครบ ✓
  - 📝 commit: `feat(1.5): add mongodb storage with indexes`

  - [x] FIX #1: ModuleNotFoundError: No module named 'pymongo' | fix: `python -m pip install pymongo`
  - [x] FIX #2: `mongodb` hostname ใช้ไม่ได้นอก Docker | fix: `docker-compose up -d mongodb` + เปลี่ยน `.env` เป็น `localhost:27057`
  - [x] FIX #3: UnicodeEncodeError ตอน print ภาษาไทยบน Windows | fix: `sys.stdout.reconfigure(encoding="utf-8")`

---

### Phase 2 — Intelligence Layer

- [x] 2.1 `rule_engine.py` — Hard Rules (3 ข้อ) + Soft Score (>= 3/5)
  - 🧪 test: `python rule_engine.py` → print passed/failed + score + reasons ✓
  - 📝 commit: `feat(2.1): add rule engine with hard+soft scoring`

- [x] 2.2 `embedder.py` — text embedding + cosine similarity 7 วัน
  - 🧪 test: `python embedder.py` → print embedding dim + top-3 similar patterns ✓
  - 📝 commit: `feat(2.2): add embedder with cosine similarity search`

- [x] 2.3 `analyzer.py` — OpenRouter LLM prompt + parse JSON output
  - 🧪 test: `python analyzer.py` → print analysis JSON ครบทุก field ✓
  - 📝 commit: `feat(2.3): add llm analyzer with structured json output`

- [x] 2.4 `risk_manager.py` — ATR × 1.2/1.5 SL/TP + RR validation
  - 🧪 test: `python risk_manager.py` → print entry/SL/TP/RR ถูกต้อง ✓
  - 📝 commit: `feat(2.4): add atr-based risk manager`

---

### Phase 3 — Output & Tracking

- [x] 3.1 `notifier.py` — Telegram SAFE ENTRY + NO TRADE messages
  - 🧪 test: `python notifier.py` → ข้อความถูกส่งใน Telegram จริง ✓

  - [x] FIX #1: 400 Bad Request — `<` ใน failed_reasons ถูกตีความเป็น HTML tag | fix: `html.escape()` บน reasons text
  - 📝 commit: `feat(3.1): add telegram notifier with safe entry and no trade`

- [x] 3.2 `outcome_tracker.py` — อัพเดต prediction_correct + result_label ("ทายถูก"/"ทายผิด") หลัง 15 นาที
  - 🧪 test: insert mock record อายุ > 15m → tracker อัพเดต outcome + result_label ได้ ✓
  - 📝 commit: `feat(3.2): add 15m outcome tracker with result_label`

  - [x] FIX #1: yfinance ไม่รองรับ `period="2h"` | fix: เปลี่ยนเป็น `period="1d"`
  - [x] FIX #2: `TimedeltaIndex.abs()` ไม่มีใน pandas version นี้ | fix: ใช้ `np.abs(secs).argmin()`

- [x] 3.3 `main.py` — startup validation + APScheduler run_cycle() ทุก 60s
  - 🧪 test: `python main.py` → เห็น log ทุก 60 วินาที ไม่ crash ✓
  - 📝 commit: `feat(3.3): add main scheduler with startup validation`

---

### Phase 4 — Deploy

- [x] 4.1 `requirements.txt` + `Dockerfile`
  - 🧪 test: `docker build -t gold-analyzer .` → build สำเร็จ ไม่มี error ✓
  - 📝 commit: `feat(4.1): add dockerfile and requirements`

  - [x] FIX #1: Dockerfile ใช้ `python:3.12-slim` แต่ packages build กับ 3.11 | fix: เปลี่ยนเป็น `python:3.11-slim` + เพิ่ม `PYTHONUNBUFFERED=1`

- [x] 4.2 `docker-compose.yml` — gold-analyzer + mongodb services
  - 🧪 test: `docker-compose up` → ทั้งสอง service up, log ปกติ ✓
  - 📝 commit: `feat(4.2): add docker-compose with mongodb`

- [x] 4.3 ทดสอบ end-to-end
  - 🧪 test: รัน 5 นาที → เห็น log ทุก 1 นาที, มี record ใน MongoDB, ถ้า signal → Telegram ส่งจริง ✓
  - 📝 commit: `feat(4.3): verified end-to-end pipeline`

---

### Phase 5 — Real-time Web Dashboard

- [x] 5.1 `web_server.py` — FastAPI + WebSocket broadcaster
  - สร้าง FastAPI app + endpoint `/ws` สำหรับ broadcast ข้อมูลทุก cycle
  - `broadcast_cycle(data)` — thread-safe ส่งจาก APScheduler thread → asyncio event loop
  - Serve `static/index.html` ที่ `/`
  - 🧪 test: `python web_server.py` → HTTP 200 + WS รับ mock data ได้ ✓
  - 📝 commit: `feat(5.1): add websocket web server`

- [x] 5.2 `static/index.html` — Dashboard 7 panels
  - Panel 1 · Price — ราคา, %, OHLCV, session, timestamp
  - Panel 2 · Indicators — RSI/MACD/BB%/EMA/ATR × 4 TF (1m/5m/15m/1h)
  - Panel 3 · Market Context — DXY/Bond/SPX/BTC/Oil + sentiment + summary
  - Panel 4 · Rule Engine — PASS/BLOCK, Hard rules ✓/✗ รายข้อ, Soft score breakdown
  - Panel 5 · Similar Patterns — top-3 จาก memory 7 วัน พร้อม result_label
  - Panel 6 · AI Analysis — direction, safety_score, confidence, reason_th (แสดงเสมอ)
  - Panel 7 · Risk Plan — entry/SL/TP/RR (แสดงเสมอ)
  - Dark theme (`#0d0d1a`) + color code: green=bullish, red=bearish, yellow=neutral
  - Flash animation เมื่อมีข้อมูลใหม่, Auto-reconnect WebSocket
  - 🧪 test: `python web_server.py` → HTTP 200 + WS รับข้อมูลและแสดงใน 7 panel ✓
  - 📝 commit: `feat(5.2): add real-time dashboard with 7 panels`

- [x] 5.3 Integrate + Update deps + Docker
  - แก้ `main.py` — เรียก `web_server.start()` + เรียก `broadcast_cycle()` ใน `run_cycle()`
  - แก้ `rule_engine.py` — เพิ่ม `hard_rules: list[dict]` ใน RuleResult
  - แก้ `requirements.txt` — เพิ่ม `fastapi==0.111.0`, `uvicorn==0.29.0`, `websockets==12.0`
  - แก้ `Dockerfile` — เพิ่ม `EXPOSE 8080`
  - แก้ `docker-compose.yml` — เพิ่ม port `8080:8080`
  - 🧪 test: import ครบ, rule_engine.hard_rules ✓, broadcast structure ถูกต้อง ✓
  - 📝 commit: `feat(5.3): integrate web dashboard into pipeline and docker`
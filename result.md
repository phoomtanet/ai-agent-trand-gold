# Gold Analyzer — สถานะระบบ

อัพเดต: 2026-05-26

---

## สถานะปัจจุบัน: ทำงานปกติ ✅

### Infrastructure

| Component | สถานะ | รายละเอียด |
|---|---|---|
| Docker gold-analyzer | ✅ Running | restart: unless-stopped |
| Docker MongoDB | ✅ Running (healthy) | port 27057:27017 |
| Web Dashboard | ✅ http://localhost:8080 | อัพเดตทุก 60 วินาที |
| Telegram Bot | ✅ Connected | ส่งข้อความได้ปกติ |

---

## Pipeline — ขั้นตอนการทำงาน (ทุก 60 วินาที)

```
Fetcher → Indicators → Market Context → Rule Engine
    → (ถ้า PASS) Embedder → LLM Analyzer → Risk Manager → Notifier
    → broadcast WebSocket → save MongoDB
```

### ผลสะสม (ณ วันนี้)

| สถานะ | จำนวน |
|---|---|
| safe_entry (AI อนุมัติ) | 1 |
| no_signal (Rule pass แต่ AI ไม่ปลอดภัย) | 25 |
| no_trade (Rule block) | 35+ |
| มี embedding | 25 |
| outcome tracked | 1+ |

---

## ระบบย่อยแต่ละส่วน

### 1. Fetcher
- ดึง XAU/USD (GC=F) + DXY / Bond / SPX / BTC / Oil จาก yfinance
- 4 timeframes: 1m, 5m, 15m, 1h
- Fallback: ถ้า GC=F ไม่มีข้อมูล ใช้ XAUUSD=X แทน

### 2. Indicators
- RSI(14), MACD(12/26/9), Bollinger Bands(20,±2σ), EMA(20/50), ATR(14)
- คำนวณทุก TF แยกกัน

### 3. Market Context
- วิเคราะห์ DXY impact, Bond impact, Risk sentiment
- ระบุ session: Asian / European / US

### 4. Rule Engine
- **Hard Rules** (ต้องผ่านทั้งหมด):
  - MACD 1m + 5m align กัน (bullish/bullish หรือ bearish/bearish)
  - RSI 1m อยู่ใน 28-75 (ไม่ extreme)
  - ATR 1m ≤ ATR 15m × 2.5 (ไม่ spike)
- **Soft Score** ≥ 3/6 จาก 5 เงื่อนไข
- ตอนนี้ส่วนใหญ่ BLOCK เพราะ MACD 1m ≠ 5m (ตลาดไม่มีทิศทางชัด)

### 5. Embedder
- สร้าง embedding (3072 dim) จาก OpenRouter (gemini-embedding-2-preview)
- หา top-3 similar patterns จาก MongoDB 7 วันล่าสุด

### 6. LLM Analyzer
- ใช้ google/gemini-2.5-flash-lite ผ่าน OpenRouter
- Output: direction, safety_score, confidence, reason_th, entry/SL/TP
- Safety override: ถ้า score < 6 หรือ confidence < 60 → is_safe_entry = false

### 7. Risk Manager
- SL = ATR × 1.2, TP = ATR × 1.5
- R:R minimum 1.0

### 8. Notifier (Telegram)
- SAFE ENTRY: ส่งเมื่อ safety ≥ 6 + R:R ≥ 1.0
- NO TRADE: ปิดอยู่ (NOTIFY_NO_TRADE=false)
- Started ✅: ส่งทุกครั้งที่ระบบ restart

### 9. Outcome Tracker
- รันทุก 5 นาที
- อัพเดต prediction_correct หลัง 15 นาที
- label: "ทายถูก" / "ทายผิด" / "ทายผิด (ราคาแทบไม่ขยับ)"

### 10. Web Dashboard
- 7 panels: Price, Indicators, Market Context, Rule Engine, Similar Patterns, AI Analysis, Risk Plan
- Dark theme, flash animation, auto-reconnect WebSocket

---

## Environment Variables หลัก

| Variable | ค่า |
|---|---|
| OPENROUTER_MODEL | google/gemini-2.5-flash-lite |
| SAFETY_SCORE_THRESHOLD | 6 |
| CONFIDENCE_THRESHOLD | 60 |
| FETCH_INTERVAL_SEC | 60 |
| NOTIFY_NO_TRADE | false |

---

## Bugs ที่แก้แล้ว

| Bug | วิธีแก้ |
|---|---|
| LLM ส่ง JSON ขาด (unterminated string) | _extract_json() repair + fallback dict |
| websockets==12.0 conflict กับ yfinance | เปลี่ยนเป็น websockets>=13.0 |
| startup message แสดงเป็น ERROR | แยก send_startup() ออกจาก send_error() |
| GC=F ไม่มีข้อมูลตอนตลาดปิด | fallback XAUUSD=X + extend period |
| Telegram 400 Bad Request | html.escape() ทุก dynamic content |

---

## วิธีรัน

```bash
# Production (Docker)
docker-compose up -d

# Local (ทดสอบ)
cd apps/gold-analyzer
python main.py          # pipeline จริง + dashboard
python web_server.py    # dashboard อย่างเดียว (mock data)

# Dashboard
http://localhost:8080
```

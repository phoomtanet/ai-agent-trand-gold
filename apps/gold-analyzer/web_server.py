from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_app = FastAPI(title="Gold Analyzer Dashboard")
_loop: Optional[asyncio.AbstractEventLoop] = None
_clients: set[WebSocket] = set()
_clients_lock = threading.Lock()
_latest: dict = {}

_STATIC = Path(__file__).parent / "static"


# ─── Static ───────────────────────────────────────────────────────────────────

@_app.get("/")
async def index():
    return FileResponse(_STATIC / "index.html")

_app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


# ─── WebSocket ────────────────────────────────────────────────────────────────

@_app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    with _clients_lock:
        _clients.add(ws)
    # ส่ง snapshot ล่าสุดทันทีเมื่อ client เชื่อมต่อ
    if _latest:
        try:
            await ws.send_text(json.dumps(_latest, ensure_ascii=False, default=str))
        except Exception:
            pass
    try:
        while True:
            await ws.receive_text()   # keep-alive ping
    except WebSocketDisconnect:
        pass
    finally:
        with _clients_lock:
            _clients.discard(ws)


async def _broadcast(data: dict) -> None:
    _latest.update(data)
    text = json.dumps(data, ensure_ascii=False, default=str)
    dead: set[WebSocket] = set()
    with _clients_lock:
        targets = set(_clients)
    for ws in targets:
        try:
            await ws.send_text(text)
        except Exception:
            dead.add(ws)
    with _clients_lock:
        _clients.difference_update(dead)


def broadcast_cycle(data: dict) -> None:
    """Thread-safe — เรียกจาก APScheduler thread ได้เลย"""
    if _loop and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(_broadcast(data), _loop)


# ─── Server lifecycle ─────────────────────────────────────────────────────────

def start(host: str = "0.0.0.0", port: int = 8080) -> None:
    """รันใน background thread — เรียกจาก main.py"""
    global _loop

    def _run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        config = uvicorn.Config(
            _app, host=host, port=port,
            loop="none", log_level="warning",
        )
        server = uvicorn.Server(config)
        _loop.run_until_complete(server.serve())

    t = threading.Thread(target=_run, daemon=True, name="web-server")
    t.start()
    print(f"[web_server] Dashboard → http://localhost:{port}")


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, time
    sys.stdout.reconfigure(encoding="utf-8")

    # ── สร้าง placeholder index.html ถ้ายังไม่มี ──
    _STATIC.mkdir(exist_ok=True)
    _html = _STATIC / "index.html"
    if not _html.exists():
        _html.write_text(
            "<html><body style='background:#0d0d1a;color:#e8e8ff'>"
            "<h2>Gold Analyzer — connecting...</h2>"
            "<script>const ws=new WebSocket('ws://'+location.host+'/ws');"
            "ws.onmessage=e=>document.body.innerHTML='<pre>'+JSON.stringify(JSON.parse(e.data),null,2)+'</pre>';"
            "</script></body></html>",
            encoding="utf-8",
        )
        print("[web_server] Created placeholder index.html")

    start()
    print("[web_server] Server started — press Ctrl+C to stop")

    # broadcast mock data ทุก 3 วินาทีเพื่อทดสอบ
    import random
    cycle = 0
    try:
        while True:
            time.sleep(3)
            cycle += 1
            mock = {
                "type": "cycle_update",
                "cycle": cycle,
                "timestamp": "2026-05-26T09:12:23Z",
                "price": {"value": round(4523 + random.uniform(-5, 5), 2),
                          "change_1m": round(random.uniform(-0.1, 0.1), 3),
                          "session": "European",
                          "ohlcv": {"open": 4522, "high": 4526, "low": 4521, "close": 4523, "volume": 0}},
                "rule_engine": {"passed": False, "soft_score": 0,
                                "failed_reasons": ["Soft score 0/6 < 3"],
                                "hard_rules": [
                                    {"name": "MACD 1m+5m", "passed": True,  "detail": "bullish"},
                                    {"name": "RSI",        "passed": True,  "detail": "46 ∈ [28,75]"},
                                    {"name": "ATR",        "passed": True,  "detail": "not spiked"},
                                ]},
                "analysis": None,
                "risk": None,
            }
            broadcast_cycle(mock)
            print(f"[web_server] Broadcast cycle #{cycle}")
    except KeyboardInterrupt:
        print("\n[web_server] Stopped")

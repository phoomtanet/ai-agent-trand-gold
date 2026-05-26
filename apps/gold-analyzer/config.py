import os
import sys
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"[config] ERROR: {key} is required but not set")
        sys.exit(1)
    return val


def _bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


# OpenRouter
OPENROUTER_API_KEY: str   = _require("OPENROUTER_API_KEY")
OPENROUTER_MODEL: str     = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")
EMBEDDING_MODEL: str      = os.getenv("EMBEDDING_MODEL",  "google/gemini-embedding-2-preview")
OPENROUTER_BASE_URL: str  = "https://openrouter.ai/api/v1"

# MongoDB
MONGODB_URI: str  = os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
MONGODB_DB: str   = os.getenv("MONGODB_DB",  "gold_analyzer")

# Telegram
TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: str   = _require("TELEGRAM_CHAT_ID")
NOTIFY_NO_TRADE: bool   = _bool("NOTIFY_NO_TRADE", False)

# Gold Analyzer — Data
GOLD_TICKER: str              = os.getenv("GOLD_TICKER", "GC=F")
ENABLE_MARKET_CONTEXT: bool   = _bool("ENABLE_MARKET_CONTEXT", True)
FETCH_INTERVAL_SEC: int       = int(os.getenv("FETCH_INTERVAL_SEC", "60"))

# Gold Analyzer — Tuning
SAFETY_SCORE_THRESHOLD: int    = int(os.getenv("SAFETY_SCORE_THRESHOLD",    "6"))
CONFIDENCE_THRESHOLD: int      = int(os.getenv("CONFIDENCE_THRESHOLD",      "60"))
MIN_RR_RATIO: float            = float(os.getenv("MIN_RR_RATIO",            "1.0"))
EMBEDDING_LOOKBACK_DAYS: int   = int(os.getenv("EMBEDDING_LOOKBACK_DAYS",   "7"))
TOP_K_SIMILAR: int             = int(os.getenv("TOP_K_SIMILAR",             "3"))


def validate() -> None:
    print("=" * 45)
    print("  Gold Analyzer — Config")
    print("=" * 45)
    print(f"  OPENROUTER_MODEL          : {OPENROUTER_MODEL}")
    print(f"  EMBEDDING_MODEL           : {EMBEDDING_MODEL}")
    print(f"  MONGODB_URI               : {MONGODB_URI}")
    print(f"  MONGODB_DB                : {MONGODB_DB}")
    print(f"  TELEGRAM_CHAT_ID          : {TELEGRAM_CHAT_ID}")
    print(f"  NOTIFY_NO_TRADE           : {NOTIFY_NO_TRADE}")
    print(f"  GOLD_TICKER               : {GOLD_TICKER}")
    print(f"  ENABLE_MARKET_CONTEXT     : {ENABLE_MARKET_CONTEXT}")
    print(f"  FETCH_INTERVAL_SEC        : {FETCH_INTERVAL_SEC}")
    print(f"  SAFETY_SCORE_THRESHOLD    : {SAFETY_SCORE_THRESHOLD}")
    print(f"  CONFIDENCE_THRESHOLD      : {CONFIDENCE_THRESHOLD}")
    print(f"  MIN_RR_RATIO              : {MIN_RR_RATIO}")
    print(f"  EMBEDDING_LOOKBACK_DAYS   : {EMBEDDING_LOOKBACK_DAYS}")
    print(f"  TOP_K_SIMILAR             : {TOP_K_SIMILAR}")
    print("=" * 45)
    print("  [OK] All required vars loaded")
    print("=" * 45)


if __name__ == "__main__":
    validate()

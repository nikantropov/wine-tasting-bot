import os
from pathlib import Path

# ====== TELEGRAM BOT ======
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Telegram ID администраторов (узнайте свой у @userinfobot)
ADMIN_IDS: list[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "1214258573").split(",")
]

# ====== DATABASE (Neon PostgreSQL) ======
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/wine_tasting"
)

# ====== WEBHOOK ======
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://wine-tasting-bot.onrender.com")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

# ====== REMINDERS ======
REMINDER_HOURS_BEFORE = int(os.getenv("REMINDER_HOURS_BEFORE", "2"))

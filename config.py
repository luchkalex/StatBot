import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
TIMEZONE = "Europe/Kiev"
GEMINI_API_KEY_SECONDARY = os.getenv("GEMINI_API_KEY_SECONDARY")
ACCESS_KEYS = {
    "key1": "stats_account1.csv",
    "key2": "stats_account2.csv"
}

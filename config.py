import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
DATABASE_URL: str = os.environ["DATABASE_URL"]
# Normalize to postgresql+asyncpg:// for SQLAlchemy async (handles both Railway formats)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

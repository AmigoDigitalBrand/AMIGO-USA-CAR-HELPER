import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
DATABASE_URL: str = os.environ["DATABASE_URL"]
# Railway provides DATABASE_URL as postgres://, SQLAlchemy needs postgresql+asyncpg://
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

from datetime import datetime, timezone
from sqlalchemy import BigInteger, Column, Float, Integer, LargeBinary, String, Text, DateTime, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class CarfaxReport(Base):
    __tablename__ = "carfax_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vin = Column(String(17), unique=True, nullable=False, index=True)
    telegram_user_id = Column(BigInteger, nullable=True)
    raw_text = Column(Text, nullable=True)
    pdf_file = Column(LargeBinary, nullable=True)          # BYTEA — binary PDF for web rendering
    ai_analysis_ro = Column(Text, nullable=True)
    ai_analysis_ru = Column(Text, nullable=True)
    ai_analysis_en = Column(Text, nullable=True)
    tokens_in  = Column(Integer, default=0, nullable=False, server_default="0")
    tokens_out = Column(Integer, default=0, nullable=False, server_default="0")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


async def init_db() -> None:
    """Create tables and apply any missing column migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migrations — ADD COLUMN IF NOT EXISTS is safe to run every time
        for sql in [
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS tokens_in  INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS tokens_out INTEGER NOT NULL DEFAULT 0",
        ]:
            await conn.execute(text(sql))

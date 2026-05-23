from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Boolean, Column, Float, Integer,
    LargeBinary, Numeric, String, Text, DateTime, text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class CarfaxReport(Base):
    __tablename__ = "carfax_reports"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    vin               = Column(String(17), unique=True, nullable=False, index=True)
    telegram_user_id  = Column(BigInteger, nullable=True)
    raw_text          = Column(Text, nullable=True)
    pdf_file          = Column(LargeBinary, nullable=True)
    ai_analysis_ro    = Column(Text, nullable=True)
    ai_analysis_ru    = Column(Text, nullable=True)
    ai_analysis_en    = Column(Text, nullable=True)
    tokens_in         = Column(Integer, default=0, nullable=False, server_default="0")
    tokens_out        = Column(Integer, default=0, nullable=False, server_default="0")
    bmw_equipment     = Column(Text, nullable=True)

    # ── Client info ──────────────────────────────────────────────────────────
    client_name       = Column(String(200), nullable=True)
    client_phone      = Column(String(30),  nullable=True, index=True)
    client_code       = Column(String(250), nullable=True)   # auto: NAME-LAST4

    # ── Procurement & pricing ────────────────────────────────────────────────
    is_procured       = Column(Boolean, default=False, nullable=False, server_default="false")
    price_car_usd      = Column(Numeric(12, 2), nullable=True)
    price_auction_usd  = Column(Numeric(12, 2), nullable=True)
    price_transfer_usd = Column(Numeric(12, 2), nullable=True)
    price_shipping_usd = Column(Numeric(12, 2), nullable=True)
    price_customs_usd  = Column(Numeric(12, 2), nullable=True)
    price_broker_usd   = Column(Numeric(12, 2), nullable=True)
    admin_notes        = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


async def init_db() -> None:
    """Create tables and apply any missing column migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for sql in [
            # legacy columns
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS tokens_in    INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS tokens_out   INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS bmw_equipment TEXT",
            # client info
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS client_name  VARCHAR(200)",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS client_phone VARCHAR(30)",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS client_code  VARCHAR(250)",
            "CREATE INDEX IF NOT EXISTS ix_carfax_client_phone ON carfax_reports (client_phone)",
            # procurement
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS is_procured       BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS price_car_usd      NUMERIC(12,2)",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS price_auction_usd  NUMERIC(12,2)",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS price_transfer_usd NUMERIC(12,2)",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS price_shipping_usd NUMERIC(12,2)",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS price_customs_usd  NUMERIC(12,2)",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS price_broker_usd   NUMERIC(12,2)",
            "ALTER TABLE carfax_reports ADD COLUMN IF NOT EXISTS admin_notes        TEXT",
        ]:
            await conn.execute(text(sql))

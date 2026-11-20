import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://finguard:finguard@localhost:5432/finguard",
)

_connect_args = (
    {"options": "-c lock_timeout=3000 -c statement_timeout=10000"}
    if DATABASE_URL.startswith("postgresql")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("FINGUARD_DB_POOL_SIZE", "20")),
    max_overflow=int(os.getenv("FINGUARD_DB_MAX_OVERFLOW", "30")),
    pool_recycle=int(os.getenv("FINGUARD_DB_POOL_RECYCLE", "1800")),
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

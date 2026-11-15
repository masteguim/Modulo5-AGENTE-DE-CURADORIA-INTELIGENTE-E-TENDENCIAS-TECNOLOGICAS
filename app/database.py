import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Configure DATABASE_URL com a conexão do PostgreSQL.")
if make_url(DATABASE_URL).drivername != "postgresql+psycopg":
    raise RuntimeError("DATABASE_URL deve usar PostgreSQL com o driver psycopg.")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()

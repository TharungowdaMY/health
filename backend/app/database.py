from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    # SQLite: allow use from FastAPI's threadpool (local dev / tests only)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # PostgreSQL (or any client-server DB): real connection pooling.
    # pool_pre_ping transparently replaces connections the server dropped
    # (e.g. Neon suspending an idle compute) instead of erroring on first use.
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

"""
bootstrap.py - container entrypoint.

1. Waits for the database to accept connections (Postgres can take a few
   seconds to start even after its container is 'up').
2. Creates tables if they don't exist.
3. Optionally seeds synthetic demo data (SEED_DEMO_DATA=true).
4. Replaces itself with uvicorn, so uvicorn is PID 1 and receives
   SIGTERM from `docker stop` directly (clean shutdown).

Written in Python rather than a shell script on purpose: no CRLF/LF
line-ending problems when the repo is cloned on Windows.
"""
import os
import sys
import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def wait_for_db(engine, attempts=30, delay=2):
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("[bootstrap] database is ready", flush=True)
            return
        except OperationalError as exc:
            print(f"[bootstrap] waiting for database ({attempt}/{attempts}): {type(exc).__name__}", flush=True)
            time.sleep(delay)
    sys.exit("[bootstrap] database never became ready - check DELTA_HEALTH_DB / DATABASE_URL")


def main():
    from app.database import Base, engine
    from app import models  # noqa: F401  (importing registers the tables on Base)

    wait_for_db(engine)
    Base.metadata.create_all(bind=engine)
    print("[bootstrap] tables ready", flush=True)

    if os.environ.get("SEED_DEMO_DATA", "false").lower() == "true":
        import seed
        if seed.main():
            print("[bootstrap] demo data seeded", flush=True)
        seed.db.close()

    port = os.environ.get("PORT", "8000")
    print(f"[bootstrap] starting uvicorn on :{port}", flush=True)
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port])


if __name__ == "__main__":
    main()

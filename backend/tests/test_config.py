"""Configuration must fail closed. Run in subprocesses because config reads env vars at import time."""
import os
import subprocess
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(code, **env_overrides):
    env = {k: v for k, v in os.environ.items()
           if k not in ("DELTA_HEALTH_ENV", "DELTA_HEALTH_SECRET", "DELTA_HEALTH_DB", "DATABASE_URL")}
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env,
                          capture_output=True, text=True)


def test_production_refuses_the_default_secret():
    result = _run("import app.config", DELTA_HEALTH_ENV="production")
    assert result.returncode != 0
    assert "DELTA_HEALTH_SECRET" in result.stderr


def test_production_refuses_a_short_secret():
    result = _run("import app.config", DELTA_HEALTH_ENV="production", DELTA_HEALTH_SECRET="tooshort")
    assert result.returncode != 0


def test_production_accepts_a_strong_secret():
    result = _run("import app.config", DELTA_HEALTH_ENV="production", DELTA_HEALTH_SECRET="a" * 40)
    assert result.returncode == 0, result.stderr


def test_provider_style_postgres_urls_are_normalized_for_sqlalchemy():
    result = _run("import app.config as c; print(c.DATABASE_URL)", DATABASE_URL="postgres://u:p@host/db")
    assert result.stdout.strip() == "postgresql+psycopg2://u:p@host/db"

"""
config.py - central settings, all overridable via environment variables so the
same image runs unchanged on a laptop, in docker compose, and on a cloud host.

Environment variables
---------------------
DELTA_HEALTH_ENV     "development" (default) or "production". In production the
                     app refuses to start with a weak/default JWT secret.
DELTA_HEALTH_SECRET  JWT signing key. Generate with:
                     python -c "import secrets; print(secrets.token_hex(32))"
DELTA_HEALTH_DB      SQLAlchemy URL. Falls back to DATABASE_URL (what Render,
                     Neon, Railway, Heroku etc. inject), then to local SQLite.
"""
import os

ENVIRONMENT = os.environ.get("DELTA_HEALTH_ENV", "development").lower()

_DEFAULT_DEV_SECRET = "dev-secret-change-this-in-production"
SECRET_KEY = os.environ.get("DELTA_HEALTH_SECRET", _DEFAULT_DEV_SECRET)

if ENVIRONMENT == "production" and (
    SECRET_KEY == _DEFAULT_DEV_SECRET
    or SECRET_KEY.startswith("change_me")
    or len(SECRET_KEY) < 32
):
    raise RuntimeError(
        "DELTA_HEALTH_SECRET must be set to a random string of at least 32 characters "
        "when DELTA_HEALTH_ENV=production. Generate one with: "
        'python -c "import secrets; print(secrets.token_hex(32))"'
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hour shift for a clinic worker


def _normalize_db_url(url: str) -> str:
    """Hosting providers hand out 'postgres://' or 'postgresql://' URLs, but
    SQLAlchemy needs to be told which driver to use."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _normalize_db_url(
    os.environ.get("DELTA_HEALTH_DB")
    or os.environ.get("DATABASE_URL")
    or "sqlite:///./delta_health.db"
)

# outbreak detection thresholds
OUTBREAK_SPIKE_RATIO = 2.0        # today's symptom count vs 7-day baseline average
OUTBREAK_MIN_COUNT = 3            # don't alert on tiny absolute numbers
REGIONAL_ALERT_RADIUS_KM = 10.0
REGIONAL_ALERT_MIN_CLINICS = 2    # how many nearby clinics must be spiking together

# drug efficacy / resistance detection
TREATMENT_FAILURE_MIN_RECORDS = 4      # don't flag on tiny sample sizes
TREATMENT_FAILURE_MIN_CLINICS = 2      # must be seen across multiple clinics, not one doctor's bad week
TREATMENT_FAILURE_RATE_THRESHOLD = 0.5  # fraction of "no_change"/"worsened" outcomes that triggers a flag
TREATMENT_FAILURE_WINDOW_DAYS = 14

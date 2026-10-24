"""
Shared fixtures.

Tests run against a throwaway SQLite file by default. CI points
DELTA_HEALTH_DB at a real PostgreSQL service instead, so the same suite
verifies behaviour on both. The env vars must be set BEFORE importing the app.
"""
import os

os.environ.setdefault("DELTA_HEALTH_DB", "sqlite:///./test_delta_health.db")
os.environ.setdefault("DELTA_HEALTH_ENV", "development")

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app import models
from app.security import hash_password
from app.main import app

CLINIC_A = {"username": "clinic_a", "password": "pw-a-12345"}
CLINIC_B = {"username": "clinic_b", "password": "pw-b-12345"}
ADMIN = {"username": "officer", "password": "pw-admin-12345"}


@pytest.fixture(scope="session", autouse=True)
def database():
    """Fresh schema + two nearby clinics (~2 km apart, inside the 10 km
    regional-alert radius) + one login per clinic + one admin login."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        a = models.Clinic(name="Test Clinic A", city="Hubballi", lat=15.3647, lng=75.1240)
        b = models.Clinic(name="Test Clinic B", city="Hubballi", lat=15.3550, lng=75.1080)
        db.add_all([a, b])
        db.commit()
        db.refresh(a)
        db.refresh(b)
        db.add_all([
            models.User(username=CLINIC_A["username"], hashed_password=hash_password(CLINIC_A["password"]),
                        role="clinic", full_name=a.name, clinic_id=a.id),
            models.User(username=CLINIC_B["username"], hashed_password=hash_password(CLINIC_B["password"]),
                        role="clinic", full_name=b.name, clinic_id=b.id),
            models.User(username=ADMIN["username"], hashed_password=hash_password(ADMIN["password"]),
                        role="admin", full_name="Test Officer"),
        ])
        db.commit()
    finally:
        db.close()

    yield

    engine.dispose()
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        os.remove(engine.url.database)


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def credentials():
    return {"clinic_a": CLINIC_A, "clinic_b": CLINIC_B, "admin": ADMIN}


def _login_headers(client, creds):
    r = client.post("/auth/login", data=creds)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def clinic_a(client):
    return _login_headers(client, CLINIC_A)


@pytest.fixture(scope="session")
def clinic_b(client):
    return _login_headers(client, CLINIC_B)


@pytest.fixture(scope="session")
def admin(client):
    return _login_headers(client, ADMIN)


@pytest.fixture(scope="session")
def make_patient():
    def _make(**overrides):
        base = dict(age=45, bmi=26.0, resting_hr=75, fever_days=2, cough_severity=1, fatigue_score=4,
                    existing_condition=0, bp_systolic=120, at_risk=0, symptom_tags="fever")
        base.update(overrides)
        return base
    return _make


@pytest.fixture(scope="session")
def populated(client, clinic_a, clinic_b, make_patient):
    """Six fever patients at each clinic. Entering them through the API also
    exercises the local-spike detector, so both clinics end up 'spiking'."""
    for headers in (clinic_a, clinic_b):
        for i in range(6):
            r = client.post("/clinic/patients", headers=headers,
                            json=make_patient(age=30 + i * 5, bmi=24 + i, fever_days=2 + i % 3, at_risk=i % 2))
            assert r.status_code == 200, r.text

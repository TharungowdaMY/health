"""
seed.py - creates demo clinics, one admin (public health) user, one login
per clinic, and a handful of starter patient records so the dashboards
aren't empty on first run.

Usage: python3 seed.py
"""
import sys
import os
import json
import random
import datetime
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np

from app.database import Base, engine, SessionLocal
from app import models, fl_core
from app.security import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# Roughly Hubballi-Dharwad area clinics, spread within ~10km of each other
CLINICS = [
    {"name": "Sunrise Family Clinic", "city": "Hubballi", "lat": 15.3647, "lng": 75.1240},
    {"name": "Green Cross Neighborhood Clinic", "city": "Hubballi", "lat": 15.3420, "lng": 75.1400},
    {"name": "Dharwad Community Health Center", "city": "Dharwad", "lat": 15.4589, "lng": 75.0078},
    {"name": "Vidyanagar Kirana-Health Post", "city": "Hubballi", "lat": 15.3550, "lng": 75.1080},
]

random.seed(7)


def _recent_timestamp(rng, days=14):
    """Spread demo encounters across the last `days` days so the outbreak
    charts show a realistic baseline instead of one giant spike 'today'."""
    return datetime.datetime.utcnow() - datetime.timedelta(days=rng.uniform(0, days))


def make_patients(clinic_id, n, age_shift, condition_prevalence, seed):
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        age = max(1, min(95, rng.gauss(45 + age_shift, 12)))
        bmi = max(14, min(50, rng.gauss(26, 5)))
        hr = max(45, min(130, rng.gauss(75, 10)))
        fever = max(0, min(14, rng.gauss(1.5, 2)))
        cough = rng.randint(0, 3)
        fatigue = rng.randint(0, 10)
        cond = 1 if rng.random() < condition_prevalence else 0
        bp = max(80, min(200, rng.gauss(122, 15)))
        risk_score = 0.04*(age-45) + 0.08*(bmi-25) + 0.35*fever + 0.5*cough + 0.15*fatigue + 1.1*cond - 2.0
        at_risk = 1 if risk_score > 0 else 0
        tags = []
        if fever >= 1: tags.append("fever")
        if cough >= 2: tags.append("cough")
        if fatigue >= 6: tags.append("fatigue")
        rows.append(models.Patient(
            clinic_id=clinic_id, age=round(age), bmi=round(bmi, 1), resting_hr=round(hr),
            fever_days=round(fever), cough_severity=cough, fatigue_score=fatigue,
            existing_condition=cond, bp_systolic=round(bp),
            symptom_tags=",".join(tags) if tags else None, at_risk=at_risk,
            created_at=_recent_timestamp(rng),
        ))
    return rows


def warm_start_model(rounds=8):
    """Run a few real federated rounds at seed time (same math the API uses:
    local training -> outlier clipping -> sample-weighted FedAvg) so a fresh
    deployment shows a trained global model and a populated accuracy history,
    instead of an untrained baseline. Purely a demo nicety."""
    state = fl_core.get_or_create_model_state(db)
    clinics = db.query(models.Clinic).all()
    for _ in range(rounds):
        weights = json.loads(state.weights_json)
        mean = json.loads(state.mean_json)
        std = json.loads(state.std_json)
        target_round = state.round + 1

        deltas, counts = [], []
        for clinic in clinics:
            delta, local_acc, n = fl_core.train_local_from_db(db, clinic.id, weights, mean, std)
            delta_json = json.dumps(delta.tolist())
            db.add(models.DeltaSubmission(
                clinic_id=clinic.id, round=target_round, delta_json=delta_json, n_samples=n,
                local_acc=local_acc, kb_size=len(delta_json.encode()) / 1024, applied=True,
            ))
            deltas.append(delta)
            counts.append(n)

        agg = fl_core.federated_average(fl_core.clip_outlier_deltas(deltas), counts)
        new_weights = np.array(weights) + agg
        acc = fl_core.evaluate_weights(new_weights.tolist(), mean, std, fl_core.HOLDOUT_X, fl_core.HOLDOUT_Y)

        state.weights_json = json.dumps(new_weights.tolist())
        state.round = target_round
        state.updated_at = datetime.datetime.utcnow()
        db.add(models.TrainingRound(round_number=target_round, global_accuracy=acc, num_clinics=len(clinics)))
        db.commit()


def main():
    """Returns True if it seeded a fresh database, False if one already existed."""
    if db.query(models.Clinic).count() > 0:
        print("Database already seeded. Delete delta_health.db to reseed from scratch.")
        return False

    clinic_rows = []
    for cfg in CLINICS:
        c = models.Clinic(name=cfg["name"], city=cfg["city"], lat=cfg["lat"], lng=cfg["lng"])
        db.add(c)
        clinic_rows.append(c)
    db.commit()
    for c in clinic_rows:
        db.refresh(c)

    admin_user = models.User(
        username="healthofficer", hashed_password=hash_password("admin123"),
        role="admin", full_name="District Health Officer",
    )
    db.add(admin_user)

    demo_params = [
        (35, 0.30, 1), (0, 0.15, 2), (15, 0.25, 3), (-10, 0.10, 4),
    ]
    for i, (clinic, (age_shift, cond_prev, seed)) in enumerate(zip(clinic_rows, demo_params), start=1):
        user = models.User(
            username=f"clinic{i}", hashed_password=hash_password("clinic123"),
            role="clinic", full_name=clinic.name, clinic_id=clinic.id,
        )
        db.add(user)
        for p in make_patients(clinic.id, n=random.randint(18, 30), age_shift=age_shift,
                                condition_prevalence=cond_prev, seed=seed):
            db.add(p)

    db.commit()

    # Seed a deliberate "possible resistance" pattern across clinics 1-3
    # for demo purposes: amoxicillin for resp_infection mostly failing.
    treatment_seed = [
        (1, "amoxicillin", "resp_infection", "worsened"),
        (1, "amoxicillin", "resp_infection", "no_change"),
        (1, "amoxicillin", "resp_infection", "improved"),
        (2, "amoxicillin", "resp_infection", "worsened"),
        (2, "amoxicillin", "resp_infection", "no_change"),
        (3, "amoxicillin", "resp_infection", "worsened"),
        (3, "amoxicillin", "resp_infection", "no_change"),
        (1, "paracetamol", "fever", "improved"),
        (2, "paracetamol", "fever", "improved"),
        (2, "paracetamol", "fever", "improved"),
        (3, "paracetamol", "fever", "improved"),
    ]
    for clinic_idx, treatment, condition, outcome in treatment_seed:
        db.add(models.TreatmentRecord(
            clinic_id=clinic_rows[clinic_idx - 1].id,
            treatment_name=treatment, condition_tag=condition, outcome=outcome,
        ))
    db.commit()

    try:
        warm_start_model()
        print("Warm-started the global model with 8 federated rounds.")
    except Exception as exc:  # optional nicety: never let it block seeding
        db.rollback()
        print(f"(skipped model warm-start: {exc})")

    print("Seeded:")
    for i, c in enumerate(clinic_rows, start=1):
        print(f"  clinic login: clinic{i} / clinic123   -> {c.name} ({c.city})")
    print("  admin login:  healthofficer / admin123     -> District Health Officer")
    return True


if __name__ == "__main__":
    main()
    db.close()

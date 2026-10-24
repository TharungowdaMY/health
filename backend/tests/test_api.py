"""End-to-end API tests through FastAPI's TestClient, against a real database."""


def test_health_reports_database_up(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "up"}


# ---------- authentication & authorization ----------

def test_login_rejects_wrong_password(client):
    r = client.post("/auth/login", data={"username": "clinic_a", "password": "wrong"})
    assert r.status_code == 401


def test_login_returns_role_and_clinic(client, credentials):
    clinic = client.post("/auth/login", data=credentials["clinic_a"]).json()
    admin = client.post("/auth/login", data=credentials["admin"]).json()
    assert clinic["role"] == "clinic" and isinstance(clinic["clinic_id"], int)
    assert admin["role"] == "admin" and admin["clinic_id"] is None


def test_protected_routes_require_a_token(client):
    assert client.get("/clinic/summary").status_code == 401
    assert client.get("/admin/overview").status_code == 401


def test_roles_are_enforced_on_the_server_not_just_the_ui(client, clinic_a, admin):
    assert client.get("/admin/overview", headers=clinic_a).status_code == 403
    assert client.get("/clinic/summary", headers=admin).status_code == 403


# ---------- patient data: validation and isolation ----------

def test_impossible_vitals_are_rejected(client, clinic_a, make_patient):
    r = client.post("/clinic/patients", headers=clinic_a, json=make_patient(resting_hr=7))
    assert r.status_code == 422


def test_a_clinic_can_never_read_another_clinics_patients(client, clinic_a, clinic_b, make_patient):
    marker = 44.4  # distinctive BMI so we can recognise this exact record
    created = client.post("/clinic/patients", headers=clinic_a, json=make_patient(bmi=marker))
    assert created.status_code == 200

    seen_by_a = client.get("/clinic/patients?limit=500", headers=clinic_a).json()
    seen_by_b = client.get("/clinic/patients?limit=500", headers=clinic_b).json()
    assert any(p["bmi"] == marker for p in seen_by_a)
    assert not any(p["bmi"] == marker for p in seen_by_b)


def test_bulk_import_imports_good_rows_and_reports_bad_ones(client, clinic_a):
    csv_text = (
        "age,bmi,resting_hr,fever_days,cough_severity,fatigue_score,existing_condition,bp_systolic,at_risk\n"
        "40,25.0,70,1,1,3,0,118,0\n"
        "40,25.0,7,1,1,3,0,118,0\n"
    )
    r = client.post("/clinic/patients/bulk_import", headers=clinic_a,
                    files={"file": ("patients.csv", csv_text.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["rows_imported"], body["rows_failed"]) == (1, 1)
    assert body["errors"][0].startswith("row 3")


def test_bulk_import_rejects_a_csv_missing_required_columns(client, clinic_a):
    r = client.post("/clinic/patients/bulk_import", headers=clinic_a,
                    files={"file": ("bad.csv", b"age,bmi\n40,25\n", "text/csv")})
    assert r.status_code == 400


# ---------- AI assistant ----------

def test_predict_is_explainable_and_runs_the_differential(client, clinic_a):
    payload = dict(age=34, bmi=24, resting_hr=92, fever_days=3, cough_severity=0, fatigue_score=6,
                   existing_condition=0, bp_systolic=118,
                   high_fever=True, pain_behind_eyes=True, low_platelet=True)
    r = client.post("/clinic/predict", headers=clinic_a, json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert 0.0 <= d["risk_probability"] <= 1.0
    assert len(d["top_contributions"]) == 4
    assert d["confidence_label"] in {"Low", "Moderate", "High"}
    assert d["differential"][0]["disease"] == "Dengue (suspected)"
    assert d["recommendations"]


# ---------- federated learning round ----------

def test_full_federated_round_only_ships_deltas(client, clinic_a, clinic_b, admin, populated):
    for headers in (clinic_a, clinic_b):
        r = client.post("/clinic/train", headers=headers)
        assert r.status_code == 200, r.text
        assert 0.0 <= r.json()["local_acc"] <= 1.0
        assert r.json()["kb_transmitted"] < 5   # a handful of numbers, never patient records

    before = client.get("/admin/overview", headers=admin).json()
    assert before["pending_submissions"] == 2

    agg = client.post("/admin/aggregate", headers=admin)
    assert agg.status_code == 200, agg.text
    body = agg.json()
    assert body["clinics_included"] == 2
    assert body["round"] == before["current_round"] + 1

    after = client.get("/admin/overview", headers=admin).json()
    assert after["current_round"] == body["round"]
    assert after["pending_submissions"] == 0


# ---------- network-level signals ----------

def test_regional_outbreak_is_detected_across_nearby_clinics(client, admin, populated):
    r = client.post("/admin/alerts/check_regional", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["alert_created"] is not None
    assert body["largest_cluster_size"] >= 2


def test_treatment_failure_needs_multiple_clinics_to_raise_an_alert(client, clinic_a, clinic_b, admin):
    def log(headers, n):
        for _ in range(n):
            r = client.post("/clinic/treatments", headers=headers, json={
                "treatment_name": "azithromycin", "condition_tag": "bacterial_pneumonia", "outcome": "worsened"})
            assert r.status_code == 200, r.text

    log(clinic_a, 4)  # plenty of records and 100% failure, but only ONE clinic
    first = client.post("/admin/alerts/check_treatment_failures", headers=admin).json()
    assert first["alerts_created"] == []

    log(clinic_b, 2)  # now a second clinic sees the same failure
    second = client.post("/admin/alerts/check_treatment_failures", headers=admin).json()
    assert len(second["alerts_created"]) == 1
    assert "azithromycin" in second["alerts_created"][0]


def test_stock_advisory_maps_a_logged_disease_to_specific_supplies(client, clinic_a, admin, populated):
    for _ in range(2):
        client.post("/clinic/treatments", headers=clinic_a, json={
            "treatment_name": "paracetamol", "condition_tag": "dengue_fever", "outcome": "improved"})
    r = client.get("/admin/stock_advisory", headers=admin)
    assert r.status_code == 200, r.text
    advisory = next(a for a in r.json()["clinic_advisories"] if a["clinic_name"] == "Test Clinic A")
    assert advisory["likely_pattern"] == "Dengue (suspected)"
    assert "NS1 antigen / rapid test kits" in advisory["recommended_supplies"]


# ---------- public dashboard ----------

def test_public_endpoints_need_no_login_and_expose_no_patient_fields(client, populated):
    for path in ["/public/overview", "/public/heatmap", "/public/alerts",
                 "/public/treatments", "/public/clinics", "/public/stock_advisory"]:
        assert client.get(path).status_code == 200, path

    for row in client.get("/public/heatmap").json():
        assert not ({"age", "bmi", "resting_hr", "symptom_tags", "notes"} & set(row))


# ---------- HTML pages ----------

def test_every_page_renders(client):
    """Guards against template-engine/framework upgrades breaking page rendering."""
    for path in ["/login", "/public", "/clinic/dashboard", "/admin/dashboard",
                 "/admin/outbreak-monitor", "/admin/drug-efficacy", "/admin/stock-advisory"]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert "<html" in r.text.lower(), path

"""The differential-diagnosis layer is rule-based decision support; these tests pin its behaviour."""
import re

from app import differential


def test_dengue_pattern_ranks_dengue_first():
    symptoms = {"high_fever": True, "pain_behind_eyes": True, "low_platelet": True}
    results = differential.evaluate_differential(symptoms, fever_days=3)
    assert results[0]["disease"] == "Dengue (suspected)"
    assert results[0]["match_pct"] > 80


def test_prolonged_fever_with_chills_ranks_malaria_first():
    symptoms = {"chills_rigors": True, "high_fever": True}
    results = differential.evaluate_differential(symptoms, fever_days=8)
    assert results[0]["disease"] == "Malaria (suspected)"


def test_match_percentages_are_bounded_and_sorted():
    results = differential.evaluate_differential({"high_fever": True, "dry_cough": True}, fever_days=2)
    pcts = [r["match_pct"] for r in results]
    assert all(0 <= p <= 100 for p in pcts)
    assert pcts == sorted(pcts, reverse=True)


def test_no_symptoms_gives_no_strong_match():
    results = differential.evaluate_differential({}, fever_days=0)
    assert results[0]["match_pct"] < 15


def test_recommendations_never_contain_drug_dosages():
    """Guardrail: this tool suggests tests/classes of action, never doses."""
    for cfg in differential.DISEASES.values():
        for line in cfg["recommendations"]:
            assert not re.search(r"\d+\s?(mg|mcg|ml)\b", line.lower()), line

"""Unit and integration tests for the Industrial 3-Tier Grading Ensemble Engine."""
import pytest
from app.ensemble import (
    compute_keyword_score,
    compute_semantic_score,
    check_step_deductions,
    compute_ensemble_grade,
    extract_keywords_and_entities,
)


def test_keyword_extraction():
    rubric = "Q1 (5 marks): During positive half cycle, diode D1 conducts in forward bias; acts as closed circuit."
    kws = extract_keywords_and_entities(rubric)
    assert "positive" in kws
    assert "half" in kws
    assert "cycle" in kws
    assert "d1" in kws
    assert "forward" in kws
    assert "bias" in kws
    assert "closed" in kws
    assert "circuit" in kws


def test_keyword_score_matching():
    rubric = "Positive half cycle conduction diode D1 forward bias closed circuit"
    student = "In positive half cycle diode D1 is in forward bias and conducts like a closed circuit"
    score, matched, missing = compute_keyword_score(student, rubric)
    assert score >= 0.85
    assert "d1" in matched
    assert "forward" in matched
    assert len(missing) <= 1


def test_semantic_score_paraphrase():
    rubric = "Current is directly proportional to potential difference across conductor"
    student = "Potential difference applied across a conductor is proportional to current flowing through it"
    sem_score = compute_semantic_score(student, rubric)
    assert sem_score >= 0.70


def test_missing_units_deduction():
    rubric = "Calculate resistance: R = V/I = 10V / 2A = 5 Ohms"
    student_without_units = "R = V / I = 10 / 2 = 5"
    deductions = check_step_deductions(student_without_units, rubric)
    assert any("Missing required standard scientific units" in d for d in deductions)

    student_with_units = "R = V / I = 10V / 2A = 5 Ohms"
    deductions_ok = check_step_deductions(student_with_units, rubric)
    assert not any("Missing required standard scientific units" in d for d in deductions_ok)


def test_crossed_out_deduction():
    student_crossed = "~~V = IR = 10 * 2 = 20~~"
    deductions = check_step_deductions(student_crossed, "State Ohm's Law and formula")
    assert any("All significant work crossed out" in d for d in deductions)


def test_ensemble_composite_calculation():
    rubric = "Q1 (5 marks): Positive half cycle diode D1 conducts acts as closed circuit"
    student = "During positive half cycle diode D1 conducts and acts as a closed circuit"
    result = compute_ensemble_grade(
        student_text=student,
        rubric_text=rubric,
        raw_llm_marks=5.0,
        max_marks=5.0,
        diagram_detected=False,
        is_diagram_required=False,
    )
    assert result["awarded_marks"] >= 4.5
    assert result["keyword_score"] >= 0.80
    assert result["semantic_score"] >= 0.70
    assert result["flagged_for_review"] is False


def test_ensemble_discrepancy_flagging():
    # Student text has ZERO keywords, but hypothetical malicious/hallucinating LLM gave 5.0 marks!
    rubric = "Bridge rectifier with 4 diodes D1 D2 D3 D4 transformer and load resistor RL"
    student_gibberish = "The quick brown fox jumps over the lazy dog"
    result = compute_ensemble_grade(
        student_text=student_gibberish,
        rubric_text=rubric,
        raw_llm_marks=5.0,
        max_marks=5.0,
    )
    # The discrepancy MUST trigger a teacher review flag!
    assert result["flagged_for_review"] is True
    assert "Keyword/Reasoning discrepancy" in result["flag_reason"]
    # And the awarded marks MUST NOT be 5.0 because keyword and semantic scores are 0!
    assert result["awarded_marks"] < 3.0

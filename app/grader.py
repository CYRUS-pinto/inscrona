"""Unified grading engine — structural answer-key evaluation with ensemble scoring.

Design decisions:
- Sequential model execution (Golden Rule): load model → grade → unload.
- Two editions merged: GLM's two-pass quality check + Chandra's dual-mode backend.
- Section-aware scoring with "Best 5 of 7" university section options.
- Deterministic keyword/semantic fallback via ensemble module.
- Produces per-question grades with evidence quotes, flags, and deductions.

Usage:
from .config import GRADE_MODEL, GRADE_TIMEOUT_S, GLM_TWO_PASS
    from .ollama_client import chat
    from .schemas import LayoutBlock
    from .grader import grade_paper
    from .answer_key import parse_answer_key

    answer_key = parse_answer_key(qp_text)
    result = grade_paper(
        pages=ocr_pages,
        answer_key=answer_key,
        section_policy="best_of_7",
    )
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import settings
from .ollama_client import chat as ollama_chat
from .schemas import (
    GradeResult,
    LayoutBlock,
    QuestionGrade,
    SectionSummary,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread safety — sequential model access (Golden Rule)
# ---------------------------------------------------------------------------
_OLLAMA_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Prompt persona — multi-disciplinary chief university examiner
# ---------------------------------------------------------------------------

BASE_EXAMINER_PERSONA = """You are a strict, multi-disciplinary Chief University Examiner
with 20+ years of experience across STEM, Quantitative Sciences, Life Sciences,
and Humanities. You grade with absolute fairness and zero tolerance for ambiguity.

RULES:
1. OCR noise resilience: ignore garbled characters, focus on semantic intent.
2. Semantic intent recognition: if the student's answer clearly addresses the
   question despite surface-level errors, award marks accordingly.
3. Systematic partial credit across 5 tiers:
   - 0%: No relevant content
   - 25%: Attempted but fundamentally incorrect
   - 50%: Partially correct with significant gaps
   - 75%: Mostly correct with minor omissions
   - 100%: Complete and accurate
4. Diagram detection: if schematic artifacts, labels, or drawing-like content
   appear in OCR output, flag diagram_detected=true.
5. Evidence quotes: extract a short verbatim excerpt (max 60 chars) from the
   student's answer that justifies the award.
6. Writing style diversity: recognize paraphrases, synonyms, and structurally
   different but semantically equivalent expressions.
7. Mark allocation: never exceed max_marks for a question. Deduct for:
   - Incorrect statements that contradict correct ones
   - Missing key concepts specified in the answer key
   - Irrelevant content that wastes examiner time
"""

# ---------------------------------------------------------------------------
# Section option helpers — "Best 5 of 7" etc.
# ---------------------------------------------------------------------------


def _apply_section_policy(
    grades: List[QuestionGrade],
    policy: str = "all",
) -> List[QuestionGrade]:
    """Apply university section option policy to question grades.

    Supported policies:
    - "all": count every question (default)
    - "best_of_5": best 5 of 7 per section (standard internal exam)
    - "best_of_7": best 7 of 10 per section
    - "best_of_N": best N of M per section

    For each section, identifies questions with is_counted=False, selects the
    top N by awarded_marks, and marks the rest with selection_reason.
    """
    if policy == "all":
        for g in grades:
            g.is_counted = True
            g.selection_reason = "counted"
        return grades

    # Parse policy string
    parts = policy.split("_of_")
    if len(parts) != 2 or not parts[1].isdigit():
        logger.warning("Unknown section policy '%s', defaulting to 'all'", policy)
        return _apply_section_policy(grades, "all")

    keep_n = int(parts[1])

    # Group by section
    sections: Dict[str, List[QuestionGrade]] = {}
    for g in grades:
        sections.setdefault(g.section, []).append(g)

    result: List[QuestionGrade] = []
    for sec_id, sec_grades in sections.items():
        # Sort by awarded_marks descending (keep highest scores)
        sorted_grades = sorted(sec_grades, key=lambda x: x.awarded_marks, reverse=True)
        for i, g in enumerate(sorted_grades):
            if i < keep_n:
                g.is_counted = True
                g.selection_reason = f"top_{keep_n}_of_{len(sec_grades)}"
            else:
                g.is_counted = False
                g.selection_reason = f"dropped_{i+1}_of_{len(sec_grades)}"
            result.append(g)

    return result


# ---------------------------------------------------------------------------
# Layout segmentation — map OCR text blocks to questions
# ---------------------------------------------------------------------------


def _segment_questions(
    blocks: List[LayoutBlock],
) -> List[Dict[str, Any]]:
    """Segment layout blocks into question groups.

    Heuristic: blocks containing 'Q1', 'Q2', 'Q.1', 'Question 1' etc.
    trigger a new question boundary. Non-question blocks are appended to
    the current question context.
    """
    import re

    question_pattern = re.compile(
        r"(?:^|\s)(?:Q|Question|Que|Qu)\s*\.?\s*(\d+)",
        re.IGNORECASE,
    )

    questions: List[Dict[str, Any]] = []
    current_q: Optional[Dict[str, Any]] = None

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        match = question_pattern.search(text)
        if match:
            q_num = int(match.group(1))
            current_q = {
                "question_id": f"q{q_num}",
                "question_number": q_num,
                "section": f"section_{(q_num - 1) // 5 + 1}",
                "text_parts": [text],
                "blocks": [block],
                "page": block.page,
            }
            questions.append(current_q)
        elif current_q is not None:
            current_q["text_parts"].append(text)
            current_q["blocks"].append(block)
        else:
            # Pre-question content (header, instructions) — skip or attach to Q1
            pass

    return questions


# ---------------------------------------------------------------------------
# LLM grading — single question
# ---------------------------------------------------------------------------

_GRADING_PROMPT_TEMPLATE = """{persona}

QUESTION:
{question_text}

MARKS ALLOCATED: {max_marks}

ANSWER KEY:
{answer_key_text}

STUDENT ANSWER:
{student_answer_text}

OUTPUT FORMAT (JSON only, no markdown fences):
{{
    "awarded_marks": <number>,
    "confidence": <0.0-1.0>,
    "feedback": "<one sentence explaining the grade>",
    "evidence_quote": "<verbatim excerpt from student answer, max 60 chars>",
    "keyword_score": <0.0-1.0>,
    "semantic_score": <0.0-1.0>,
    "reasoning_score": <0.0-1.0>,
    "matched_keywords": ["<keyword1>", ...],
    "missing_keywords": ["<keyword1>", ...],
    "deductions": ["<reason1>", ...],
    "diagram_detected": false,
    "flag_for_review": false,
    "flag_reason": ""
}}

Be strict. If the answer is incorrect, award 0. If partially correct, award
proportional marks. Never exceed {max_marks}.
"""


def _grade_single_question(
    question: Dict[str, Any],
    answer_key_entry: Dict[str, Any],
    model: str,
    timeout_s: int,
) -> QuestionGrade:
    """Grade a single question via LLM call."""
    question_text = " ".join(question["text_parts"])
    max_marks = answer_key_entry.get("max_marks", 5)
    answer_key_text = answer_key_entry.get("answer_text", "No answer key provided.")
    student_answer_text = question_text if question_text else "No answer provided."

    prompt = _GRADING_PROMPT_TEMPLATE.format(
        persona=BASE_EXAMINER_PERSONA,
        question_text=question.get("question_id", "Unknown"),
        max_marks=max_marks,
        answer_key_text=answer_key_text,
        student_answer_text=student_answer_text,
    )

    raw_response = ""
    try:
        with _OLLAMA_LOCK:
            response = ollama_chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 1024, "temperature": 0.1},
            )
            raw_response = response.get("message", {}).get("content", "")
    except Exception as exc:
        logger.error("LLM grading failed for %s: %s", question.get("question_id"), exc)
        return QuestionGrade(
            question_id=question.get("question_id", "unknown"),
            section=question.get("section", "unknown"),
            awarded_marks=0,
            max_marks=max_marks,
            confidence=0.0,
            feedback=f"Grading failed: {exc}",
            evidence_quote="",
            is_counted=True,
            selection_reason="llm_error",
            diagram_detected=False,
            teacher_overridden=False,
            keyword_score=0.0,
            semantic_score=0.0,
            reasoning_score=0.0,
            flagged_for_review=True,
            flag_reason=f"LLM error: {exc}",
            matched_keywords=[],
            missing_keywords=[],
            deductions=[],
        )

    # Parse JSON response
    parsed = _parse_llm_response(raw_response)

    # Clamp awarded_marks to max_marks
    awarded = max(0, min(int(parsed.get("awarded_marks", 0)), max_marks))

    return QuestionGrade(
        question_id=question.get("question_id", "unknown"),
        section=question.get("section", "unknown"),
        awarded_marks=awarded,
        max_marks=max_marks,
        confidence=float(parsed.get("confidence", 0.5)),
        feedback=parsed.get("feedback", ""),
        evidence_quote=parsed.get("evidence_quote", "")[:60],
        is_counted=True,
        selection_reason="counted",
        diagram_detected=bool(parsed.get("diagram_detected", False)),
        teacher_overridden=False,
        keyword_score=float(parsed.get("keyword_score", 0.0)),
        semantic_score=float(parsed.get("semantic_score", 0.0)),
        reasoning_score=float(parsed.get("reasoning_score", 0.0)),
        flagged_for_review=bool(parsed.get("flag_for_review", False)),
        flag_reason=parsed.get("flag_reason", ""),
        matched_keywords=parsed.get("matched_keywords", []),
        missing_keywords=parsed.get("missing_keywords", []),
        deductions=parsed.get("deductions", []),
    )


def _parse_llm_response(raw: str) -> Dict[str, Any]:
    """Extract JSON from LLM response, handling markdown fences and noise."""
    import re

    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    # Try direct JSON parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the response
    json_match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try to find JSON object with nested braces
    depth = 0
    start = None
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(cleaned[start : i + 1])
                except json.JSONDecodeError:
                    start = None

    logger.warning("Failed to parse LLM response as JSON: %s", raw[:200])
    return {
        "awarded_marks": 0,
        "confidence": 0.0,
        "feedback": "Failed to parse grading response",
        "evidence_quote": "",
        "keyword_score": 0.0,
        "semantic_score": 0.0,
        "reasoning_score": 0.0,
        "matched_keywords": [],
        "missing_keywords": [],
        "deductions": [],
        "diagram_detected": False,
        "flag_for_review": True,
        "flag_reason": "LLM response parse failure",
    }


# ---------------------------------------------------------------------------
# Ensemble scoring — deterministic fallback
# ---------------------------------------------------------------------------


def _ensemble_score(
    question: Dict[str, Any],
    answer_key_entry: Dict[str, Any],
    llm_grade: QuestionGrade,
) -> QuestionGrade:
    """Apply ensemble 3-tier scoring as calibration/fallback.

    Tier 1: Keyword matching (0.25 weight)
    Tier 2: Semantic overlap (0.35 weight)
    Tier 3: LLM reasoning (0.40 weight)
    """
    try:
        from .ensemble import (
            extract_keywords_and_entities,
            STOPWORDS,
        )
    except ImportError:
        logger.debug("Ensemble module not available, using LLM scores only")
        return llm_grade

    student_text = " ".join(question.get("text_parts", [])).lower()
    answer_text = answer_key_entry.get("answer_text", "").lower()

    # Tier 1: Keyword matching
    student_kw = extract_keywords_and_entities(student_text)
    answer_kw = extract_keywords_and_entities(answer_text)
    if answer_kw:
        matched = student_kw & answer_kw
        keyword_score = len(matched) / len(answer_kw) if answer_kw else 0.0
    else:
        keyword_score = 0.0
        matched = set()

    # Tier 2: Semantic overlap (word-level Jaccard as proxy)
    student_words = set(student_text.split()) - STOPWORDS
    answer_words = set(answer_text.split()) - STOPWORDS
    if answer_words:
        semantic_score = len(student_words & answer_words) / len(answer_words)
    else:
        semantic_score = 0.0

    # Tier 3: LLM reasoning score (already computed)
    reasoning_score = llm_grade.reasoning_score

    # Calibrated composite
    W_KW, W_SEM, W_LLM = 0.25, 0.35, 0.40
    calibrated = (
        W_KW * keyword_score + W_SEM * semantic_score + W_LLM * reasoning_score
    )

    # Update LLM grade with ensemble calibration
    llm_grade.keyword_score = keyword_score
    llm_grade.semantic_score = semantic_score
    llm_grade.reasoning_score = reasoning_score
    llm_grade.matched_keywords = sorted(matched)

    # Flag if ensemble disagrees significantly with LLM
    llm_norm = llm_grade.awarded_marks / llm_grade.max_marks if llm_grade.max_marks else 0
    discrepancy = abs(llm_norm - calibrated)
    if discrepancy > 0.3 and not llm_grade.flagged_for_review:
        llm_grade.flagged_for_review = True
        llm_grade.flag_reason = (
            f"Ensemble-LLM discrepancy: {discrepancy:.2f} "
            f"(ensemble={calibrated:.2f}, llm_norm={llm_norm:.2f})"
        )

    return llm_grade


# ---------------------------------------------------------------------------
# Two-pass quality check (from GLM edition)
# ---------------------------------------------------------------------------

_PASS2_PROMPT_TEMPLATE = """{persona}

This is a HIGH-ACCURACY re-grading pass. The initial grading pass scored this
question with low confidence ({initial_confidence:.2f}).

QUESTION:
{question_text}

MARKS ALLOCATED: {max_marks}

ANSWER KEY:
{answer_key_text}

STUDENT ANSWER:
{student_answer_text}

INITIAL GRADE: {initial_awarded}/{max_marks}

Review the initial grade carefully. Check for:
1. Semantic equivalence (paraphrases, synonyms)
2. Partial credit opportunities
3. Incorrect deductions
4. Missing key concepts

OUTPUT FORMAT (JSON only, no markdown fences):
{{
    "awarded_marks": <number>,
    "confidence": <0.0-1.0>,
    "feedback": "<one sentence explaining the grade>",
    "evidence_quote": "<verbatim excerpt from student answer, max 60 chars>",
    "keyword_score": <0.0-1.0>,
    "semantic_score": <0.0-1.0>,
    "reasoning_score": <0.0-1.0>,
    "matched_keywords": ["<keyword1>", ...],
    "missing_keywords": ["<keyword1>", ...],
    "deductions": ["<reason1>", ...],
    "diagram_detected": false,
    "flag_for_review": false,
    "flag_reason": ""
}}
"""


def _pass2_regrade(
    question: Dict[str, Any],
    answer_key_entry: Dict[str, Any],
    initial_grade: QuestionGrade,
    model: str,
    timeout_s: int,
) -> QuestionGrade:
    """Second-pass re-grading for low-confidence answers."""
    question_text = " ".join(question.get("text_parts", []))
    max_marks = answer_key_entry.get("max_marks", 5)

    prompt = _PASS2_PROMPT_TEMPLATE.format(
        persona=BASE_EXAMINER_PERSONA,
        question_text=question.get("question_id", "Unknown"),
        max_marks=max_marks,
        answer_key_text=answer_key_entry.get("answer_text", "No answer key."),
        student_answer_text=question_text,
        initial_confidence=initial_grade.confidence,
        initial_awarded=initial_grade.awarded_marks,
    )

    raw_response = ""
    try:
        with _OLLAMA_LOCK:
            response = ollama_chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 1024, "temperature": 0.05},
            )
            raw_response = response.get("message", {}).get("content", "")
    except Exception as exc:
        logger.error("Pass-2 regrading failed for %s: %s", question.get("question_id"), exc)
        return initial_grade  # Fall back to initial grade

    parsed = _parse_llm_response(raw_response)
    new_awarded = max(0, min(int(parsed.get("awarded_marks", 0)), max_marks))

    # Only accept pass-2 result if it's more confident
    new_confidence = float(parsed.get("confidence", 0.0))
    if new_confidence > initial_grade.confidence:
        logger.info(
            "Pass-2 improved %s: %d/%d (conf %.2f→%.2f)",
            question.get("question_id"),
            new_awarded,
            max_marks,
            initial_grade.confidence,
            new_confidence,
        )
        return QuestionGrade(
            question_id=initial_grade.question_id,
            section=initial_grade.section,
            awarded_marks=new_awarded,
            max_marks=max_marks,
            confidence=new_confidence,
            feedback=parsed.get("feedback", initial_grade.feedback),
            evidence_quote=parsed.get("evidence_quote", "")[:60],
            is_counted=initial_grade.is_counted,
            selection_reason=initial_grade.selection_reason,
            diagram_detected=bool(parsed.get("diagram_detected", False)),
            teacher_overridden=False,
            keyword_score=float(parsed.get("keyword_score", 0.0)),
            semantic_score=float(parsed.get("semantic_score", 0.0)),
            reasoning_score=float(parsed.get("reasoning_score", 0.0)),
            flagged_for_review=bool(parsed.get("flag_for_review", False)),
            flag_reason=parsed.get("flag_reason", ""),
            matched_keywords=parsed.get("matched_keywords", []),
            missing_keywords=parsed.get("missing_keywords", []),
            deductions=parsed.get("deductions", []),
        )

    return initial_grade


# ---------------------------------------------------------------------------
# Main grading entry point
# ---------------------------------------------------------------------------


def grade_paper(
    pages: List[Dict[str, Any]],
    answer_key: Dict[str, Any],
    layout_blocks: Optional[List[LayoutBlock]] = None,
    section_policy: str = "all",
    model: Optional[str] = None,
    timeout_s: Optional[int] = None,
    enable_pass2: bool = True,
    pass2_threshold: float = 0.55,
) -> GradeResult:
    """Grade a complete answer sheet against an answer key.

    Args:
        pages: List of OCR page results [{"page": int, "text": str, "confidence": float}, ...]
        answer_key: Parsed answer key from answer_key.parse_answer_key()
        layout_blocks: Optional pre-computed layout blocks (if None, uses OCR text directly)
        section_policy: Section option policy ("all", "best_of_5", "best_of_7")
        model: Override grading model (default: GRADE_MODEL)
        timeout_s: Override timeout (default: GRADE_TIMEOUT_S)
        enable_pass2: Enable two-pass quality check (default: True)
        pass2_threshold: Confidence threshold for pass-2 (default: 0.55)

    Returns:
        GradeResult with per-question grades and section summaries.
    """
    model = model or GRADE_MODEL
    timeout_s = timeout_s or GRADE_TIMEOUT_S

    start_time = time.time()

    # Build full OCR text from pages
    full_text = "\n\n".join(
        f"--- Page {p.get('page', i+1)} ---\n{p.get('text', '')}"
        for i, p in enumerate(pages)
    )

    # Segment into questions (using layout blocks if available, else heuristic)
    if layout_blocks:
        question_groups = _segment_questions(layout_blocks)
    else:
        # Fallback: treat entire text as one block, attempt segmentation
        from .schemas import LayoutBlock as LB

        synthetic_blocks = [
            LB(
                block_id=f"synthetic_{i}",
                type="text",
                page=p.get("page", i + 1),
                text=p.get("text", ""),
                confidence=p.get("confidence", 0.0),
                bbox=(0, 0, 0, 0),
            )
            for i, p in enumerate(pages)
        ]
        question_groups = _segment_questions(synthetic_blocks)

    # Map answer key questions
    answer_key_questions = answer_key.get("questions", {})

    # Grade each question
    question_grades: List[QuestionGrade] = []

    for q_group in question_groups:
        q_id = q_group["question_id"]

        # Find matching answer key entry
        answer_entry = answer_key_questions.get(q_id)
        if answer_entry is None:
            # Try numeric match
            q_num = q_group.get("question_number")
            if q_num and str(q_num) in answer_key_questions:
                answer_entry = answer_key_questions[str(q_num)]
            else:
                # No answer key — flag for review
                question_grades.append(
                    QuestionGrade(
                        question_id=q_id,
                        section=q_group.get("section", "unknown"),
                        awarded_marks=0,
                        max_marks=0,
                        confidence=0.0,
                        feedback="No answer key found for this question",
                        evidence_quote="",
                        is_counted=False,
                        selection_reason="no_answer_key",
                        diagram_detected=False,
                        teacher_overridden=False,
                        keyword_score=0.0,
                        semantic_score=0.0,
                        reasoning_score=0.0,
                        flagged_for_review=True,
                        flag_reason="Missing answer key",
                        matched_keywords=[],
                        missing_keywords=[],
                        deductions=[],
                    )
                )
                continue

        # Grade via LLM
        llm_grade = _grade_single_question(
            q_group, answer_entry, model=model, timeout_s=timeout_s
        )

        # Apply ensemble calibration
        calibrated_grade = _ensemble_score(q_group, answer_entry, llm_grade)

        # Two-pass quality check for low-confidence grades
        if (
            enable_pass2
            and calibrated_grade.confidence < pass2_threshold
            and GLM_TWO_PASS
        ):
            logger.info(
                "Pass-2 triggered for %s (confidence %.2f < %.2f)",
                q_id,
                calibrated_grade.confidence,
                pass2_threshold,
            )
            calibrated_grade = _pass2_regrade(
                q_group, answer_entry, calibrated_grade, model=model, timeout_s=timeout_s
            )

        question_grades.append(calibrated_grade)

    # Apply section policy (Best 5 of 7 etc.)
    question_grades = _apply_section_policy(question_grades, section_policy)

    # Compute section summaries
    section_totals: Dict[str, Dict[str, float]] = {}
    for g in question_grades:
        sec = g.section
        if sec not in section_totals:
            section_totals[sec] = {"awarded": 0.0, "possible": 0.0}
        if g.is_counted:
            section_totals[sec]["awarded"] += g.awarded_marks
            section_totals[sec]["possible"] += g.max_marks

    section_summaries: List[SectionSummary] = []
    for sec_id, totals in section_totals.items():
        awarded = totals["awarded"]
        possible = totals["possible"]
        section_summaries.append(
            SectionSummary(
                section_id=sec_id,
                rule_applied=section_policy,
                selected_questions=[
                    g.question_id for g in question_grades
                    if g.section == sec_id and g.is_counted
                ],
                dropped_questions=[
                    g.question_id for g in question_grades
                    if g.section == sec_id and not g.is_counted
                ],
                raw_total=awarded,
                total_possible=possible,
                percentage=(awarded / possible * 100) if possible > 0 else 0.0,
                flags=[
                    g.question_id for g in question_grades
                    if g.section == sec_id and g.flagged_for_review
                ],
            )
        )

    # Overall totals (counted questions only)
    total_awarded = sum(g.awarded_marks for g in question_grades if g.is_counted)
    total_possible = sum(g.max_marks for g in question_grades if g.is_counted)
    overall_confidence = (
        sum(g.confidence for g in question_grades if g.is_counted)
        / max(1, sum(1 for g in question_grades if g.is_counted))
    )

    elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "Grading complete: %d/%d marks (%.1f%%) in %dms [%d questions, %d flagged]",
        total_awarded,
        total_possible,
        (total_awarded / total_possible * 100) if total_possible > 0 else 0,
        elapsed_ms,
        len(question_grades),
        sum(1 for g in question_grades if g.flagged_for_review),
    )

    return GradeResult(
        total_marks=total_awarded,
        total_possible=total_possible,
        percentage=(total_awarded / total_possible * 100) if total_possible > 0 else 0.0,
        confidence=overall_confidence,
        question_grades=question_grades,
        section_summaries=section_summaries,
        model_used=model,
        elapsed_ms=elapsed_ms,
        pass2_used=enable_pass2 and GLM_TWO_PASS,
        pass2_count=sum(
            1 for g in question_grades
            if g.confidence >= pass2_threshold  # Was regraded and improved
        ),
    )

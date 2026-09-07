"""
Ensemble grading engine: 3-tier scoring pipeline.
Tier 1: Deterministic Keyword (0.25)
Tier 2: Semantic Concept Overlap (0.35)
Tier 3: Chain-of-Thought LLM (0.40)
"""

import math
import re
from typing import Optional

from . import config
from .schemas import QuestionGrade, GradeResult

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than",
    "too", "very", "just", "because", "but", "and", "or", "if", "while",
    "that", "this", "these", "those", "it", "its", "what", "which", "who",
    "whom", "he", "she", "they", "them", "his", "her", "their", "we",
    "our", "you", "your", "my", "me", "i", "am", "about", "up", "out",
    "it's", "don't", "doesn't", "didn't", "won't", "wouldn't", "couldn't",
    "shouldn't", "isn't", "aren't", "wasn't", "weren't",
}


def extract_keywords_and_entities(text: str) -> set[str]:
    """Extract keywords and named entities from text (case-insensitive)."""
    text = text.lower()
    # Simple tokenization
    tokens = re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", text)
    keywords = {t for t in tokens if t not in STOPWORDS and len(t) > 1}
    return keywords


def _tier1_keyword(student_text: str, answer_text: str) -> float:
    """Deterministic keyword overlap score (Jaccard-like)."""
    student_kw = extract_keywords_and_entities(student_text)
    answer_kw = extract_keywords_and_entities(answer_text)

    if not answer_kw:
        return 0.0

    intersection = student_kw & answer_kw
    # Use Jaccard-like: intersection / answer_keywords (recall-oriented)
    return len(intersection) / len(answer_kw) if answer_kw else 0.0


def _tier2_semantic(student_text: str, answer_text: str) -> float:
    """Semantic concept overlap using simple bag-of-words cosine similarity."""
    student_kw = extract_keywords_and_entities(student_text)
    answer_kw = extract_keywords_and_entities(answer_text)

    if not answer_kw or not student_kw:
        return 0.0

    # Simple cosine similarity on keyword sets
    intersection = student_kw & answer_kw
    if not intersection:
        return 0.0

    # Cosine similarity approximation
    mag_s = math.sqrt(len(student_kw))
    mag_a = math.sqrt(len(answer_kw))
    if mag_s == 0 or mag_a == 0:
        return 0.0

    return len(intersection) / (mag_s * mag_a)


def _tier3_llm(student_text: str, answer_text: str, max_marks: int, ollama_client) -> dict:
    """Chain-of-Thought LLM grading via Ollama."""
    prompt = f"""You are an expert examiner. Grade the student answer against the model answer.

MARKS ALLOTTED: {max_marks}

MODEL ANSWER:
{answer_text}

STUDENT ANSWER:
{student_text}

Grade fairly. Return ONLY a JSON object:
{{"marks": <0 to {max_marks}>, "confidence": <0.0 to 1.0>, "reasoning": "<brief explanation>"}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        result = ollama_client.chat(
            model=config.GRADE_MODEL,
            messages=messages,
            keep_alive="30m",
            timeout_s=config.GRADE_TIMEOUT_S,
        )
        response_text = result.get("message", {}).get("content", "{}")
        # Try to parse JSON from response
        import json
        # Find JSON in response
        match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"marks": 0, "confidence": 0.0, "reasoning": "Could not parse LLM response"}
    except Exception as e:
        return {"marks": 0, "confidence": 0.0, "reasoning": f"LLM error: {str(e)}"}


def grade_question(
    student_text: str,
    answer_text: str,
    max_marks: int,
    ollama_client=None,
    question_id: str = "",
    pass2_threshold: float = 0.55,
) -> QuestionGrade:
    """Grade a single question using the 3-tier ensemble."""
    # Tier 1: Keyword
    t1_score = _tier1_keyword(student_text, answer_text)

    # Tier 2: Semantic
    t2_score = _tier2_semantic(student_text, answer_text)

    # Combined T1+T2 deterministic score
    deterministic = (0.25 * t1_score) + (0.35 * t2_score)

    # Tier 3: LLM (only if deterministic score is below threshold or LLM client provided)
    t3_marks = 0
    t3_confidence = 0.0
    t3_reasoning = "Skipped (deterministic sufficient)"

    if ollama_client and (deterministic < pass2_threshold or config.GLM_TWO_PASS):
        llm_result = _tier3_llm(student_text, answer_text, max_marks, ollama_client)
        t3_marks = llm_result.get("marks", 0)
        t3_confidence = llm_result.get("confidence", 0.0)
        t3_reasoning = llm_result.get("reasoning", "")

    # Final score: weighted combination
    # Deterministic mapped to marks range
    det_marks = round(deterministic * max_marks)

    if t3_confidence > 0.5:
        # LLM confident — blend deterministic and LLM
        final_marks = round(0.5 * det_marks + 0.5 * t3_marks)
    else:
        # LLM not confident or skipped — use deterministic
        final_marks = det_marks

    final_marks = max(0, min(final_marks, max_marks))

    return QuestionGrade(
        question_id=question_id,
        marks=final_marks,
        max_marks=max_marks,
        keyword_score=round(t1_score, 4),
        semantic_score=round(t2_score, 4),
        llm_marks=t3_marks,
        llm_confidence=round(t3_confidence, 4),
        reasoning=t3_reasoning,
    )


def grade_all_questions(
    questions: list[dict],
    answer_key: dict,
    ollama_client=None,
) -> GradeResult:
    """Grade all questions and produce overall result.

    questions: list of {"question_id": str, "student_text": str, "max_marks": int}
    answer_key: {"question_id": {"model_answer": str, "max_marks": int}}
    """
    question_grades = []

    for q in questions:
        qid = q.get("question_id", "")
        student_text = q.get("student_text", "")
        max_marks = q.get("max_marks", 10)

        answer_entry = answer_key.get(qid, {})
        answer_text = answer_entry.get("model_answer", "")
        if not answer_text:
            answer_text = answer_entry.get("answer", "")

        grade = grade_question(
            student_text=student_text,
            answer_text=answer_text,
            max_marks=max_marks,
            ollama_client=ollama_client,
            question_id=qid,
        )
        question_grades.append(grade)

    total_marks = sum(q.marks for q in question_grades)
    max_total = sum(q.max_marks for q in question_grades)

    return GradeResult(
        question_grades=question_grades,
        total_marks=total_marks,
        max_total=max_total,
        overall_confidence=round(
            sum(q.llm_confidence for q in question_grades) / max(len(question_grades), 1), 4
        ),
    )

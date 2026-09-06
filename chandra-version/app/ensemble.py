"""Industrial 3-Tier Grading Ensemble Engine for Inscrona.

Combines:
  1. Tier 1: Deterministic Technical Keyword & Entity Matching (weight: 0.25)
  2. Tier 2: Semantic Concept & Clause Overlap (weight: 0.35)
  3. Tier 3: Chain-of-Thought LLM Step Reasoning (weight: 0.40)

Produces calibrated composite marks, step-marking deductions, and automated
teacher-review flags whenever discrepancy exceeds tolerance.
"""
import re
import math
from typing import Dict, List, Optional, Tuple, Set


# Common academic stopwords to ignore during keyword extraction
STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at", "from",
    "by", "for", "with", "about", "against", "between", "into", "through", "during",
    "before", "after", "above", "below", "to", "of", "in", "on", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "can",
    "could", "should", "would", "may", "might", "must", "shall", "will", "marks", "mark",
    "question", "q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10", "part",
    "section", "explain", "state", "describe", "calculate", "derive", "find", "determine"
}


def extract_keywords_and_entities(text: str) -> Set[str]:
    """Extracts critical technical keywords, component labels, and numerical values."""
    if not text:
        return set()

    # 1. Technical acronyms, component labels (D1, D2, RL, AC, DC, PN, Vout)
    tokens = re.findall(r"\b[A-Z0-9_]{1,6}\b|\b[A-Za-z]{3,}\b|\b\d+(?:\.\d+)?\b", text)
    cleaned = set()
    for tok in tokens:
        lower = tok.lower()
        if lower not in STOPWORDS and len(lower) > 1:
            cleaned.add(lower)
    return cleaned


def compute_keyword_score(student_text: str, rubric_text: str) -> Tuple[float, List[str], List[str]]:
    """Tier 1: Deterministic Technical Keyword Coverage.
    Returns (score [0.0 - 1.0], matched_keywords, missing_keywords).
    """
    if not student_text or not student_text.strip():
        return 0.0, [], list(extract_keywords_and_entities(rubric_text))

    rubric_kws = extract_keywords_and_entities(rubric_text)
    if not rubric_kws:
        return 1.0, [], []

    student_lower = student_text.lower()
    matched = []
    missing = []

    for kw in rubric_kws:
        # Check exact word boundary or stem match
        pattern = r"\b" + re.escape(kw)
        if re.search(pattern, student_lower):
            matched.append(kw)
        else:
            # Check prefix/stem match (e.g. "conduct" vs "conduction" vs "conducts")
            stem = kw[:5] if len(kw) >= 5 else kw
            if stem in student_lower:
                matched.append(kw)
            else:
                missing.append(kw)

    score = len(matched) / len(rubric_kws) if rubric_kws else 1.0
    return round(score, 3), matched, missing


def compute_semantic_score(student_text: str, rubric_text: str) -> float:
    """Tier 2: Semantic Concept & Phrase Overlap.
    Evaluates n-gram co-occurrence, key phrase overlap, and technical bigrams.
    """
    if not student_text or not student_text.strip():
        return 0.0

    s_clean = re.sub(r"[^\w\s]", " ", student_text.lower())
    r_clean = re.sub(r"[^\w\s]", " ", rubric_text.lower())

    s_words = [w for w in s_clean.split() if w not in STOPWORDS]
    r_words = [w for w in r_clean.split() if w not in STOPWORDS]

    if not r_words:
        return 1.0
    if not s_words:
        return 0.0

    # 1. Unigram Jaccard similarity
    s_set = set(s_words)
    r_set = set(r_words)
    intersection = s_set.intersection(r_set)
    union = s_set.union(r_set)
    unigram_jaccard = len(intersection) / len(union) if union else 0.0

    # 2. Bigram coverage (captures relationships like "forward bias", "closed circuit", "half cycle")
    s_bigrams = set(zip(s_words[:-1], s_words[1:])) if len(s_words) > 1 else set()
    r_bigrams = set(zip(r_words[:-1], r_words[1:])) if len(r_words) > 1 else set()
    
    bigram_match = 0.0
    if r_bigrams:
        matched_bigrams = s_bigrams.intersection(r_bigrams)
        bigram_match = len(matched_bigrams) / len(r_bigrams)

    # 3. Rubric coverage ratio (what % of rubric concepts are covered in student text)
    rubric_recall = len(intersection) / len(r_set) if r_set else 0.0

    # Composite semantic score
    semantic_score = (0.35 * unigram_jaccard) + (0.35 * bigram_match) + (0.30 * rubric_recall)
    return round(min(1.0, semantic_score * 1.5), 3)


def check_step_deductions(student_text: str, rubric_text: str) -> List[str]:
    """Identifies specific academic step-marking omissions & deductions."""
    deductions = []
    if not student_text or not student_text.strip():
        return ["Unanswered: 0 marks"]

    s_lower = student_text.lower()
    r_lower = rubric_text.lower()

    # Check units omission if calculation/formula question with numerical units
    has_numerical_rubric = bool(re.search(r"\b\d+\s*(?:v|volts?|a|amps?|ohms?|omega|w|watts?|hz|%)\b", r_lower))
    if has_numerical_rubric:
        has_student_unit = bool(re.search(r"\b\d+\s*(?:v|volts?|a|amps?|ohms?|omega|w|watts?|hz|%)\b", s_lower)) or any(re.search(r"\d+\s*" + re.escape(c), student_text) for c in ["Ω", "V", "A", "%"])
        if not has_student_unit:
            deductions.append("Missing required standard scientific units (-0.5 marks)")

    # Check crossed-out work with no clean replacement
    if "~~" in student_text:
        uncanceled = re.sub(r"~~.*?~~", "", student_text).strip()
        if len(uncanceled) < 15:
            deductions.append("All significant work crossed out; no uncanceled replacement found")

    return deductions


def compute_ensemble_grade(
    student_text: str,
    rubric_text: str,
    raw_llm_marks: float,
    max_marks: float,
    diagram_detected: bool = False,
    is_diagram_required: bool = False,
) -> Dict[str, any]:
    """Combines Tier 1 (Keywords), Tier 2 (Semantic), and Tier 3 (LLM) into calibrated grade."""
    kw_score, matched_kws, missing_kws = compute_keyword_score(student_text, rubric_text)
    sem_score = compute_semantic_score(student_text, rubric_text)

    # Normalize LLM score
    llm_norm = min(1.0, max(0.0, raw_llm_marks / max_marks)) if max_marks > 0 else 0.0

    # Weighted Ensemble: 0.25 Keywords, 0.35 Semantic, 0.40 LLM
    raw_ensemble = (0.25 * kw_score) + (0.35 * sem_score) + (0.40 * llm_norm)

    # Diagram bonus/penalty if question is schematic-dependent
    if is_diagram_required and diagram_detected:
        raw_ensemble = min(1.0, raw_ensemble + 0.10)
    elif is_diagram_required and not diagram_detected and not any(w in student_text.lower() for w in ["d1", "circuit", "schematic", "node"]):
        raw_ensemble = max(0.0, raw_ensemble - 0.20)

    deductions = check_step_deductions(student_text, rubric_text)
    if "Missing required standard scientific units (-0.5 marks)" in deductions:
        unit_penalty = min(0.5, max_marks * 0.1)
        awarded = max(0.0, (raw_ensemble * max_marks) - unit_penalty)
    else:
        awarded = raw_ensemble * max_marks

    # Round to standard 0.25 / 0.5 step grading standard
    calibrated_marks = round(round(awarded * 2) / 2, 2)  # Rounds to nearest 0.5
    calibrated_marks = min(max_marks, max(0.0, calibrated_marks))

    # Flag for teacher review gate
    flagged = False
    flag_reason = None

    # Discrepancy check between deterministic keywords and LLM reasoning
    discrepancy = abs(kw_score - llm_norm)
    if discrepancy > 0.35 and max_marks >= 3.0:
        flagged = True
        flag_reason = f"Keyword/Reasoning discrepancy ({kw_score:.2f} vs {llm_norm:.2f}): verify manually"
    elif raw_ensemble < 0.60 and raw_ensemble > 0.40:
        flagged = True
        flag_reason = f"Borderline score ({calibrated_marks}/{max_marks}): teacher review suggested"
    elif "All significant work crossed out" in " ".join(deductions):
        flagged = True
        flag_reason = "Crossed-out draft requires human confirmation"

    confidence = round(min(1.0, max(0.4, (0.5 * kw_score + 0.5 * sem_score) if matched_kws else 0.5)), 2)

    return {
        "awarded_marks": calibrated_marks,
        "max_marks": max_marks,
        "keyword_score": kw_score,
        "semantic_score": sem_score,
        "reasoning_score": round(llm_norm, 3),
        "confidence": confidence,
        "flagged_for_review": flagged,
        "flag_reason": flag_reason,
        "matched_keywords": matched_kws,
        "missing_keywords": missing_kws,
        "deductions": deductions,
        "ensemble_formula": "Final = 0.25*Keyword + 0.35*Semantic + 0.40*LLM",
    }

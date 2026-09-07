"""
Feedback generation engine: produces detailed student feedback from grading results.
"""

from typing import Optional

from .schemas import GradeResult, QuestionGrade


def generate_feedback(
    grade_result: GradeResult,
    answer_key: dict,
    student_name: str = "Student",
) -> dict:
    """Generate comprehensive feedback for a graded paper."""
    question_feedback = []

    for qg in grade_result.question_grades:
        qf = _generate_question_feedback(qg, answer_key)
        question_feedback.append(qf)

    # Overall assessment
    percentage = (grade_result.total_marks / grade_result.max_total * 100) if grade_result.max_total > 0 else 0
    grade = _compute_grade(percentage)

    # Strengths and weaknesses
    strengths = [qf for qf in question_feedback if qf["percentage"] >= 70]
    weaknesses = [qf for qf in question_feedback if qf["percentage"] < 40]

    # Summary
    summary = _generate_summary(
        student_name=student_name,
        total_marks=grade_result.total_marks,
        max_total=grade_result.max_total,
        percentage=percentage,
        grade=grade,
        strengths=strengths,
        weaknesses=weaknesses,
        confidence=grade_result.overall_confidence,
    )

    return {
        "student_name": student_name,
        "total_marks": grade_result.total_marks,
        "max_total": grade_result.max_total,
        "percentage": round(percentage, 2),
        "grade": grade,
        "overall_confidence": grade_result.overall_confidence,
        "summary": summary,
        "question_feedback": question_feedback,
        "strengths": [s["question_id"] for s in strengths],
        "weaknesses": [w["question_id"] for w in weaknesses],
    }


def _generate_question_feedback(qg: QuestionGrade, answer_key: dict) -> dict:
    """Generate feedback for a single question."""
    percentage = (qg.marks / qg.max_marks * 100) if qg.max_marks > 0 else 0

    answer_entry = answer_key.get(qg.question_id, {})
    model_answer = answer_entry.get("model_answer", "")
    rubric = answer_entry.get("rubric", "")

    # Determine feedback level
    if percentage >= 80:
        level = "excellent"
        comment = f"Excellent work on this question. You scored {qg.marks}/{qg.max_marks}."
    elif percentage >= 60:
        level = "good"
        comment = f"Good attempt. You scored {qg.marks}/{qg.max_marks}."
    elif percentage >= 40:
        level = "needs_improvement"
        comment = f"Needs improvement. You scored {qg.marks}/{qg.max_marks}."
    else:
        level = "poor"
        comment = f"Requires significant improvement. You scored {qg.marks}/{qg.max_marks}."

    # Add specific feedback
    if qg.llm_confidence > 0.5 and qg.reasoning:
        comment += f" {qg.reasoning}"

    # Suggest improvements
    suggestions = []
    if percentage < 100:
        if qg.keyword_score < 0.5:
            suggestions.append("Review key terminology and concepts")
        if qg.semantic_score < 0.5:
            suggestions.append("Focus on explaining the core concepts more clearly")

    return {
        "question_id": qg.question_id,
        "marks": qg.marks,
        "max_marks": qg.max_marks,
        "percentage": round(percentage, 2),
        "level": level,
        "comment": comment,
        "suggestions": suggestions,
        "keyword_score": qg.keyword_score,
        "semantic_score": qg.semantic_score,
    }


def _compute_grade(percentage: float) -> str:
    """Convert percentage to letter grade."""
    if percentage >= 90:
        return "A+"
    elif percentage >= 80:
        return "A"
    elif percentage >= 70:
        return "B+"
    elif percentage >= 60:
        return "B"
    elif percentage >= 50:
        return "C+"
    elif percentage >= 40:
        return "C"
    elif percentage >= 30:
        return "D"
    else:
        return "F"


def _generate_summary(
    student_name: str,
    total_marks: int,
    max_total: int,
    percentage: float,
    grade: str,
    strengths: list,
    weaknesses: list,
    confidence: float,
) -> str:
    """Generate a human-readable summary."""
    lines = [
        f"Dear {student_name},",
        "",
        f"You have scored {total_marks}/{max_total} ({percentage:.1f}%), earning a grade of {grade}.",
        "",
    ]

    if strengths:
        qids = ", ".join(s["question_id"] for s in strengths[:3])
        lines.append(f"Strengths: You performed well on {qids}.")

    if weaknesses:
        qids = ", ".join(w["question_id"] for w in weaknesses[:3])
        lines.append(f"Areas for improvement: {qids}.")

    if confidence < 0.6:
        lines.append("")
        lines.append("Note: Some answers were difficult to read. Please ensure your handwriting is clear for future exams.")

    lines.append("")
    lines.append("Keep up the effort! Consistent practice will improve your performance.")

    return "\n".join(lines)


def generate_brief_feedback(grade_result: GradeResult) -> str:
    """Generate a one-line brief feedback."""
    percentage = (grade_result.total_marks / grade_result.max_total * 100) if grade_result.max_total > 0 else 0
    grade = _compute_grade(percentage)
    return f"Score: {grade_result.total_marks}/{grade_result.max_total} ({percentage:.1f}%) — Grade: {grade}"

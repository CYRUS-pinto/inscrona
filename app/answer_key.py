"""
Answer key management: loading, parsing, validation.
Supports JSON and plain-text formats.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AnswerKeyEntry:
    question_id: str
    model_answer: str
    max_marks: int
    keywords: list[str] | None = None
    rubric: str | None = None


@dataclass
class AnswerKey:
    title: str
    subject: str
    total_marks: int
    entries: list[AnswerKeyEntry]

    def get_entry(self, question_id: str) -> Optional[AnswerKeyEntry]:
        """Look up an answer by question ID."""
        for e in self.entries:
            if e.question_id == question_id:
                return e
        return None

    def to_dict(self) -> dict:
        """Convert to dict format expected by grader."""
        return {
            e.question_id: {
                "model_answer": e.model_answer,
                "max_marks": e.max_marks,
                "keywords": e.keywords or [],
                "rubric": e.rubric or "",
            }
            for e in self.entries
        }


def load_answer_key(path: str) -> AnswerKey:
    """Load answer key from a JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Answer key not found: {path}")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _parse_answer_key(data)


def load_answer_key_from_dict(data: dict) -> AnswerKey:
    """Load answer key from a dictionary (e.g., API request)."""
    return _parse_answer_key(data)


def _parse_answer_key(data: dict) -> AnswerKey:
    """Parse answer key from dict."""
    title = data.get("title", "Untitled Answer Key")
    subject = data.get("subject", "General")
    total_marks = data.get("total_marks", 0)
    questions = data.get("questions", data.get("entries", []))

    entries = []
    for q in questions:
        qid = q.get("question_id", q.get("id", ""))
        answer = q.get("model_answer", q.get("answer", ""))
        marks = q.get("max_marks", q.get("marks", 10))
        keywords = q.get("keywords", None)
        rubric = q.get("rubric", None)

        entries.append(AnswerKeyEntry(
            question_id=qid,
            model_answer=answer,
            max_marks=marks,
            keywords=keywords,
            rubric=rubric,
        ))

    # Auto-calculate total if not provided
    if total_marks == 0:
        total_marks = sum(e.max_marks for e in entries)

    return AnswerKey(
        title=title,
        subject=subject,
        total_marks=total_marks,
        entries=entries,
    )


def validate_answer_key(answer_key: AnswerKey) -> list[str]:
    """Validate an answer key. Returns list of warnings."""
    warnings = []

    if not answer_key.entries:
        warnings.append("Answer key has no questions")

    for entry in answer_key.entries:
        if not entry.question_id:
            warnings.append(f"Entry missing question ID: {entry.model_answer[:50]}...")
        if not entry.model_answer.strip():
            warnings.append(f"Question {entry.question_id}: empty model answer")
        if entry.max_marks <= 0:
            warnings.append(f"Question {entry.question_id}: invalid max marks ({entry.max_marks})")

    # Check for duplicate IDs
    ids = [e.question_id for e in answer_key.entries]
    dupes = [qid for qid in ids if ids.count(qid) > 1]
    if dupes:
        warnings.append(f"Duplicate question IDs: {set(dupes)}")

    return warnings


def create_sample_answer_key() -> AnswerKey:
    """Create a sample answer key for testing."""
    return AnswerKey(
        title="Sample Exam Answer Key",
        subject="General",
        total_marks=100,
        entries=[
            AnswerKeyEntry(
                question_id="Q1",
                model_answer="Photosynthesis is the process by which green plants convert light energy into chemical energy, producing glucose from carbon dioxide and water.",
                max_marks=10,
                keywords=["photosynthesis", "light energy", "chemical energy", "glucose", "carbon dioxide", "water"],
                rubric="2 marks for definition, 4 marks for process explanation, 2 marks for equation, 2 marks for importance",
            ),
            AnswerKeyEntry(
                question_id="Q2",
                model_answer="Newton's three laws of motion describe the relationship between force and motion. First law: an object at rest stays at rest. Second law: F=ma. Third law: every action has an equal and opposite reaction.",
                max_marks=10,
                keywords=["Newton", "laws", "motion", "force", "inertia", "F=ma", "action", "reaction"],
                rubric="3 marks per law, 1 mark for correct terminology",
            ),
        ],
    )

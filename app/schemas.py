"""
schemas.py — Pydantic models for Inscrona engine pipeline.

Defines the data contracts for OCR → Structural Analysis → Grading.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────── Enums ────────────────────────────


class QuestionStatus(str, Enum):
    """Per-question evaluation status."""
    FULLY_CORRECT = "fully_correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"
    NOT_ATTEMPTED = "not_attempted"


class ReviewFlag(str, Enum):
    """Flags raised during grading for human review."""
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    CROSS_PAGE_DELEGATION = "cross_page_delegation"
    FEEDBACK_MISMATCH = "feedback_mismatch"
    LOW_CONFIDENCE = "low_confidence"
    COMPOSITE_CONFIDENCE = "composite_confidence"
    COMPOSITE_CORRECTNESS = "composite_correctness"
    LOW_DETAIL = "low_detail"
    VERY_SHORT = "very_short"
    NEGATIVE = "negative"


# ──────────────────────────── OCR ─────────────────────────────


class PageOcr(BaseModel):
    """Per-page OCR result."""
    page_index: int
    image_path: str | None = None
    text: str = ""
    raw_ocr: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class OcrResult(BaseModel):
    """Aggregate OCR result across all pages."""
    job_id: str
    student_id: str | None = None
    pages: list[PageOcr] = Field(default_factory=list)
    full_text: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def reassemble_text(self) -> str:
        """Join page text with page markers."""
        return "\n\n".join(
            f"--- PAGE {p.page_index + 1} ---\n{p.text}"
            for p in sorted(self.pages, key=lambda x: x.page_index)
        )


# ──────────────────────────── Structural ──────────────────────


class AnswerSegment(BaseModel):
    """One attempt at answering a question."""
    question_id: str
    text: str = ""
    page_index: int = 0
    bbox: tuple[int, int, int, int] | None = None
    marks_awarded: float = 0.0
    marks_possible: float = 0.0
    confidence: float = 0.0


class SectionSummary(BaseModel):
    """Summary for a major section (e.g., Part A, Part B)."""
    section_id: str
    label: str = ""
    total_marks: float = 0.0
    scored_marks: float = 0.0
    question_count: int = 0


# ──────────────────────────── Grading ─────────────────────────


class QuestionGrade(BaseModel):
    """Per-question grading result."""
    question_id: str
    status: QuestionStatus = QuestionStatus.NOT_ATTEMPTED
    marks_possible: float = 0.0
    marks_awarded: float = 0.0
    confidence: float = 0.0
    feedback: str = ""
    answer_text: str = ""
    keywords_matched: list[str] = Field(default_factory=list)
    keywords_missed: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    tier_scores: dict[str, float] = Field(default_factory=dict)
    raw_llm_response: str = ""


class FeedbackItem(BaseModel):
    """Structured feedback for a question or section."""
    question_id: str | None = None
    section_id: str | None = None
    strength: str = ""
    weakness: str = ""
    recommendation: str = ""
    points_detail: str = ""


class GradeResult(BaseModel):
    """Complete grading result for a submission."""
    job_id: str
    student_id: str | None = None
    question_grades: list[QuestionGrade] = Field(default_factory=list)
    section_summaries: list[SectionSummary] = Field(default_factory=list)
    feedback: list[FeedbackItem] = Field(default_factory=list)
    total_marks: float = 0.0
    scored_marks: float = 0.0
    percentage: float = 0.0
    confidence: float = 0.0
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ──────────────────────────── Layout ──────────────────────────


class LayoutBlock(BaseModel):
    """Detected region on a page."""
    block_id: str = ""
    block_type: str = "unknown"  # text, image, table, equation, diagram
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    text: str = ""
    page_index: int = 0
    children: list[LayoutBlock] = Field(default_factory=list)


# ──────────────────────────── Audit ───────────────────────────


class AuditEntry(BaseModel):
    """Audit trail record."""
    job_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = ""
    entry_hash: str = ""


class PsychometricReport(BaseModel):
    """Item-level psychometric analysis."""
    job_id: str
    total_students: int = 0
    item_count: int = 0
    mean_score: float = 0.0
    median_score: float = 0.0
    std_dev: float = 0.0
    item_difficulty: dict[str, float] = Field(default_factory=dict)
    item_discrimination: dict[str, float] = Field(default_factory=dict)
    pass_count: int = 0
    fail_count: int = 0
    pass_rate: float = 0.0
    reliability_index: float = 0.0


# ──────────────────────────── Job ─────────────────────────────


class JobStatus(str, Enum):
    QUEUED = "queued"
    OCR = "ocr"
    STRUCTURE = "structure"
    GRADING = "grading"
    COMPLETE = "complete"
    FAILED = "failed"


class Job(BaseModel):
    """Processing job state."""
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    current_stage: str = ""
    student_id: str | None = None
    total_pages: int = 0
    total_questions: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error: str | None = None
    result_path: str | None = None
    marks_possible: float = 0.0
    marks_awarded: float = 0.0
    percentage: float = 0.0
    ocr_result: OcrResult | None = None
    grade_result: GradeResult | None = None


class JobCreateResponse(BaseModel):
    """Response returned upon successfully creating a grading job."""
    job_id: str
    status: str
    message: str = "Grading started"


class JobStatusResponse(BaseModel):
    """Status details of an ongoing or completed job."""
    job_id: str
    filename: str = ""
    pages: int = 0
    status: str = "pending"
    progress: float = 0.0
    current_page: int = 0
    total_pages: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None


class JobListResponse(BaseModel):
    """Collection of recent jobs."""
    jobs: list[dict[str, Any]] = Field(default_factory=list)


# ──────────────────────────── Helpers ─────────────────────────


def compute_hash(data: str) -> str:
    """SHA-256 hash for audit chaining."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def safe_mark_json(obj: dict[str, Any], key: str) -> str:
    """Safely extract a string field, else 'N/A'."""
    val = obj.get(key)
    if val is None:
        return "N/A"
    if isinstance(val, str):
        return val
    return str(val)

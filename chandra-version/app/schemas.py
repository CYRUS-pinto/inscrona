"""Pydantic contracts — the single source of truth for pipeline JSON."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PageOcr(BaseModel):
    page: int
    text: str
    confidence: float = Field(ge=0, le=1)


class OcrResult(BaseModel):
    engine: str
    mode: str
    pages: List[PageOcr]
    full_text: str
    elapsed_ms: int
    confidence: float = Field(ge=0, le=1)


class LayoutBlock(BaseModel):
    block_id: str
    type: str  # PAGEHEADER, SECTIONHEADER, QUESTION, STUDENT_ANSWER, COMPLEXREGION_DIAGRAM
    page: int = 1
    text: str
    confidence: float = Field(default=0.8, ge=0, le=1)
    bbox: Optional[List[float]] = None  # [ymin, xmin, ymax, xmax] 0-100% normalized


class QuestionGrade(BaseModel):
    question_id: str = "Q1"
    section: str = "General"
    awarded_marks: float = Field(ge=0)
    max_marks: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    feedback: str = Field(default="", max_length=1000)
    evidence_quote: Optional[str] = None  # Verbatim citation from student text
    is_counted: bool = True  # False if excess in "best-of-N" option rule
    selection_reason: Optional[str] = None
    diagram_detected: bool = False
    teacher_overridden: bool = False


class SectionSummary(BaseModel):
    section_id: str
    rule_applied: str  # e.g. "Best 5 of 7 counted" or "All questions counted"
    total_answered: int
    total_counted: int
    section_awarded: float
    section_max: float


class GradeResult(BaseModel):
    grades: List[QuestionGrade]
    sections: List[SectionSummary] = []
    total_awarded: float = 0
    total_max: float = 0
    overall_confidence: float = Field(default=0, ge=0, le=1)
    summary: str = ""
    rubric_mode: str = "structured"  # "structured" | "unstructured"


class GradeResponse(BaseModel):
    submission_id: str
    job_id: Optional[str] = None
    ocr: OcrResult
    layout_blocks: List[LayoutBlock] = []
    grading: GradeResult
    flags: List[str] = []
    image_path: Optional[str] = None
    result_path: Optional[str] = None
    image_urls: List[str] = []


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    progress: int = Field(ge=0, le=100)
    stage: str
    result: Optional[GradeResponse] = None
    error: Optional[str] = None


class OverrideRequest(BaseModel):
    question_id: str
    new_marks: Optional[float] = None
    awarded_marks: Optional[float] = None
    teacher_note: Optional[str] = None
    reason: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    engine: str
    mode: str
    ollama_reachable: bool
    models: List[str]

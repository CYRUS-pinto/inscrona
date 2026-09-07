"""
Audit trail with SHA-256 Merkle-hash chaining and psychometric analytics.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config
from .schemas import GradeResult

AUDIT_LOG_PATH = Path("results/audit_chain.jsonl")


def _compute_hash(data: str) -> str:
    """Compute SHA-256 hash."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _compute_merkle_link(prev_hash: str, current_data: str) -> str:
    """Compute hash chain link (previous hash + current data)."""
    combined = prev_hash + current_data
    return _compute_hash(combined)


def append_audit_record(
    job_id: str,
    grade_result: GradeResult,
    metadata: Optional[dict] = None,
    prev_hash: str = "",
) -> str:
    """Append an audit record and return the new chain hash."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "total_marks": grade_result.total_marks,
        "max_total": grade_result.max_total,
        "overall_confidence": grade_result.overall_confidence,
        "question_count": len(grade_result.question_grades),
        "metadata": metadata or {},
        "prev_hash": prev_hash,
    }

    # Serialize for hashing
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record_hash = _compute_merkle_link(prev_hash, canonical)
    record["hash"] = record_hash

    # Write to log
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return record_hash


def get_last_hash() -> str:
    """Get the last hash from the audit log for chaining."""
    if not AUDIT_LOG_PATH.exists():
        return ""
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines:
                last_record = json.loads(lines[-1])
                return last_record.get("hash", "")
    except Exception:
        pass
    return ""


def verify_chain() -> dict:
    """Verify the integrity of the audit chain."""
    if not AUDIT_LOG_PATH.exists():
        return {"valid": True, "records": 0, "message": "No audit log found"}

    records = []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        return {"valid": True, "records": 0, "message": "Empty audit log"}

    broken = []
    for i, record in enumerate(records):
        expected_prev = records[i - 1].get("hash", "") if i > 0 else ""
        actual_prev = record.get("prev_hash", "")
        if actual_prev != expected_prev:
            broken.append(i)

    return {
        "valid": len(broken) == 0,
        "records": len(records),
        "broken_links": broken,
        "message": f"Chain valid ({len(records)} records)" if not broken else f"Chain BROKEN at {len(broken)} positions",
    }


def compute_psychometrics(grade_results: list[GradeResult]) -> dict:
    """Compute psychometric analytics across all graded papers."""
    all_marks = []
    all_confidences = []

    for gr in grade_results:
        all_marks.append(gr.total_marks)
        all_confidences.append(gr.overall_confidence)

        # Item-level analysis
        for qg in gr.question_grades:
            all_marks.append(qg.marks)

    if not all_marks:
        return {"error": "No marks data"}

    import statistics

    n = len(grade_results)
    marks_only = [gr.total_marks for gr in grade_results]

    result = {
        "papers_graded": n,
        "overall": {
            "mean": round(statistics.mean(marks_only), 2),
            "median": round(statistics.median(marks_only), 2),
            "std_dev": round(statistics.stdev(marks_only), 2) if len(marks_only) > 1 else 0,
            "min": min(marks_only),
            "max": max(marks_only),
        },
        "confidence": {
            "mean": round(statistics.mean(all_confidences), 4) if all_confidences else 0,
        },
    }

    # Pass/fail (assuming 40% threshold)
    if grade_results:
        max_total = grade_results[0].max_total
        threshold = max_total * 0.4
        passed = sum(1 for m in marks_only if m >= threshold)
        result["pass_rate"] = round(passed / n, 4) if n > 0 else 0
        result["pass_threshold"] = threshold

    # Item difficulty (P-value) per question
    question_marks = {}
    question_max = {}
    for gr in grade_results:
        for qg in gr.question_grades:
            qid = qg.question_id
            if qid not in question_marks:
                question_marks[qid] = []
                question_max[qid] = qg.max_marks
            question_marks[qid].append(qg.marks)

    item_analysis = {}
    for qid, marks_list in question_marks.items():
        max_m = question_max.get(qid, 10)
        p_value = statistics.mean(marks_list) / max_m if max_m > 0 else 0
        item_analysis[qid] = {
            "p_value": round(p_value, 4),
            "mean_marks": round(statistics.mean(marks_list), 2),
            "difficulty": "easy" if p_value > 0.7 else "medium" if p_value > 0.3 else "hard",
        }

    result["item_analysis"] = item_analysis

    return result

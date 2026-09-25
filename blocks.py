import re
from typing import List, Dict, Any, Optional

def extract_document_blocks(
    ocr_text: str,
    question_grades: Optional[List[Dict[str, Any]]] = None,
    img_width: int = 1000,
    img_height: int = 1000
) -> List[Dict[str, Any]]:
    """
    Parses OCR text and question grading into structured Datalab-style document blocks
    with normalized bounding box coordinates [ymin, xmin, ymax, xmax] (0 to 1000 scale).
    """
    if not ocr_text or not ocr_text.strip():
        return []

    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    if not lines:
        return []

    q_map = {}
    if question_grades:
        for q in question_grades:
            qid = str(q.get("question_id", "")).strip().upper()
            if qid:
                q_map[qid] = q

    blocks: List[Dict[str, Any]] = []
    
    # 1. Detect Header Block (first 1-3 lines if mentioning University, Assessment, College, Exam)
    header_lines = []
    curr_idx = 0
    header_keywords = ("university", "college", "school", "internal assessment", "exam", "name", "reg", "roll", "course")
    while curr_idx < min(len(lines), 4):
        line_lower = lines[curr_idx].lower()
        if any(kw in line_lower for kw in header_keywords) or (curr_idx == 0 and not re.match(r"^Q\d", lines[curr_idx], re.IGNORECASE)):
            header_lines.append(lines[curr_idx])
            curr_idx += 1
        else:
            break

    if header_lines:
        blocks.append({
            "id": "block_header",
            "type": "PAGEHEADER",
            "tag": "PageHeader",
            "text": "\n".join(header_lines),
            "box_2d": [30, 60, 150, 940],
            "confidence": 0.95
        })

    # 2. Parse Remaining Text into Questions and Answer Blocks
    # Find question boundary indices (e.g. Q1:, Question 1, 1., 1))
    q_pattern = re.compile(r"^(?:Q(?:uestion)?\s*(\d+[a-zA-Z]?)|(\d+)[\.\)])\s*[:\.]?", re.IGNORECASE)

    current_qid = None
    current_q_text = []
    remaining_lines = lines[curr_idx:] if curr_idx < len(lines) else []

    question_sections = []

    for line in remaining_lines:
        m = q_pattern.match(line)
        if m:
            if current_qid is not None or current_q_text:
                question_sections.append((current_qid, "\n".join(current_q_text)))
            num = m.group(1) or m.group(2)
            current_qid = f"Q{num.upper()}"
            current_q_text = [line]
        else:
            current_q_text.append(line)

    if current_q_text:
        question_sections.append((current_qid, "\n".join(current_q_text)))

    # If no explicit question markers were matched, treat as Q1 or generic handwriting blocks
    if not question_sections and remaining_lines:
        question_sections = [("Q1", "\n".join(remaining_lines))]

    # Distribute vertical space for question blocks
    start_y = 170 if header_lines else 50
    available_height = 950 - start_y
    step_y = available_height / max(len(question_sections), 1)

    for i, (qid, text) in enumerate(question_sections):
        b_ymin = int(start_y + i * step_y)
        b_ymax = int(min(970, start_y + (i + 1) * step_y - 20))
        
        # Check if diagram is mentioned
        has_diagram = "[diagram" in text.lower() or "graph" in text.lower() or "circuit" in text.lower()
        block_type = "DIAGRAM" if has_diagram else ("QUESTION" if qid else "HANDWRITING")

        q_info = q_map.get(qid.upper(), {}) if qid else {}

        block = {
            "id": f"block_{qid or f'body_{i+1}'}",
            "type": block_type,
            "tag": "Question" if qid else "Handwriting",
            "question_id": qid,
            "text": text,
            "box_2d": [b_ymin, 50, b_ymax, 950],
            "marks": q_info.get("marks_awarded"),
            "max_marks": q_info.get("max_marks"),
            "feedback": q_info.get("feedback", ""),
            "confidence": float(q_info.get("confidence", 0.85))
        }
        blocks.append(block)

    return blocks

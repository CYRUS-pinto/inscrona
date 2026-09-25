import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from PIL import Image, ImageOps

def clean_duplicate_ocr_loops(text: str) -> str:
    """Removes runaway duplicate OCR passes from models like glm-ocr."""
    if not text:
        return ""
    # Strip markdown code fence markers
    text = re.sub(r'```(?:mark|ocr)?', '', text).strip()
    
    # Check for repeated "I. PART-A" or "PART-A"
    occurrences = [m.start() for m in re.finditer(r'(?:^|\n)\s*(?:I[\.\s]+)?PART[-\s]*A', text, re.I)]
    if len(occurrences) >= 2 and occurrences[1] > 80:
        text = text[:occurrences[1]].strip()
        
    # Check for "3|Page" or page numbers
    if "3|Page" in text:
        text = text.split("3|Page")[0].strip()
    elif "3 | Page" in text:
        text = text.split("3 | Page")[0].strip()
        
    return text.strip()

def detect_physical_ink_boxes(
    image_path: Union[str, Path],
    min_block_height: int = 10,
    min_block_width: int = 40,
    dark_threshold: int = 135
) -> List[Tuple[int, int, int, int]]:
    """
    Scans a document image with Pillow to detect the actual physical ink bounding boxes
    [ymin, xmin, ymax, xmax] on a 0-1000 scale.
    Excludes ruled margins to prevent full-page margin vertical line merges.
    """
    path = Path(image_path)
    if not path.exists():
        return []

    try:
        im = Image.open(path).convert('L')
    except Exception:
        return []

    # Downscale for high-speed scanning
    scan_w, scan_h = 200, 400
    small = im.resize((scan_w, scan_h), Image.BILINEAR)
    small = ImageOps.autocontrast(small, cutoff=2)
    
    if hasattr(small, "get_flattened_data"):
        pixels = list(small.get_flattened_data())
    else:
        pixels = list(small.getdata())

    # 1. Measure horizontal row ink activity excluding margins (x: 12% to 92%)
    margin_left = int(scan_w * 0.12)
    margin_right = int(scan_w * 0.94)
    row_activity = []
    for y in range(scan_h):
        row = pixels[y * scan_w + margin_left : y * scan_w + margin_right]
        dark_count = sum(1 for p in row if p < dark_threshold)
        row_activity.append(dark_count)

    # 2. Cluster rows into vertical ink bands separated by white space
    vertical_bands = []
    in_band = False
    start_y = 0
    min_gap = 3
    gap_count = 0

    for y, count in enumerate(row_activity):
        if count >= 3:
            if not in_band:
                in_band = True
                start_y = y
            gap_count = 0
        else:
            if in_band:
                gap_count += 1
                if gap_count >= min_gap:
                    in_band = False
                    end_y = y - gap_count
                    if (end_y - start_y) >= 2:
                        vertical_bands.append((start_y, end_y))
    if in_band:
        vertical_bands.append((start_y, scan_h))

    # 3. For each vertical band, compute horizontal ink extent [xmin, xmax]
    ink_boxes = []
    for sy, ey in vertical_bands:
        col_activity = [0] * scan_w
        for y in range(sy, min(ey + 1, scan_h)):
            row = pixels[y * scan_w : (y + 1) * scan_w]
            for x, p in enumerate(row):
                if p < dark_threshold:
                    col_activity[x] += 1

        active_cols = [x for x, c in enumerate(col_activity) if c >= 1 and x >= margin_left - 10]
        if not active_cols:
            continue

        ymin = max(0, int(sy * 1000 / scan_h))
        ymax = min(1000, int(ey * 1000 / scan_h))
        xmin = max(0, int(min(active_cols) * 1000 / scan_w))
        xmax = min(1000, int(max(active_cols) * 1000 / scan_w))

        # Modest padding
        ymin = max(10, ymin - 4)
        ymax = min(990, ymax + 4)
        xmin = max(20, xmin - 6)
        xmax = min(980, xmax + 8)

        if (ymax - ymin) >= min_block_height and (xmax - xmin) >= min_block_width:
            ink_boxes.append((ymin, xmin, ymax, xmax))

    return ink_boxes


def extract_document_blocks(
    ocr_text: str,
    question_grades: Optional[List[Dict[str, Any]]] = None,
    image_path: Optional[Union[str, Path]] = None,
    img_width: int = 1000,
    img_height: int = 1000
) -> List[Dict[str, Any]]:
    """
    Parses OCR text and question grading into clean, non-overlapping document blocks.
    Deduplicates repeated OCR loop text and maps boxes to actual physical ink bands.
    """
    if not ocr_text or not ocr_text.strip():
        return []

    # Deduplicate OCR text loops first
    ocr_text = clean_duplicate_ocr_loops(ocr_text)

    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    if not lines:
        return []

    q_map = {}
    if question_grades:
        for q in question_grades:
            qid = str(q.get("question_id", "")).strip().upper()
            if qid:
                q_map[qid] = q

    # 1. Detect Header Block
    header_lines = []
    curr_idx = 0
    header_keywords = ("university", "college", "school", "internal assessment", "exam", "name", "reg", "roll", "course")
    while curr_idx < min(len(lines), 3):
        line_lower = lines[curr_idx].lower()
        if any(kw in line_lower for kw in header_keywords) or (curr_idx == 0 and not re.match(r"^[0-9QIVXLCDM]", lines[curr_idx])):
            header_lines.append(lines[curr_idx])
            curr_idx += 1
        else:
            break

    # 2. Parse into Sections and Questions
    part_pattern = re.compile(r"^(?:(?:[IVXLCDM]+\.?\s*)?(?:PART|SECTION)\s*[-–—:]?\s*([A-Za-z0-9]+))", re.IGNORECASE)
    q_pattern = re.compile(r"^(?:Q(?:uestion)?\s*(\d+[a-zA-Z]?)|(\d+)[\.\)])\s*[:\.]?", re.IGNORECASE)
    sections = []
    if header_lines:
        sections.append(("HEADER", "\n".join(header_lines), None))

    current_qid = None
    current_q_text = []
    current_section = None
    remaining_lines = lines[curr_idx:] if curr_idx < len(lines) else []

    for line in remaining_lines:
        pm = part_pattern.match(line)
        if pm:
            if current_qid is not None or current_q_text:
                sections.append((current_qid or "HANDWRITING", "\n".join(current_q_text), current_section))
                current_qid = None
                current_q_text = []
            part_letter = pm.group(1).upper()
            current_section = f"Part {part_letter}"
            sections.append(("SECTION", line, current_section))
            continue

        m = q_pattern.match(line)
        if m:
            if current_qid is not None or current_q_text:
                sections.append((current_qid or "HANDWRITING", "\n".join(current_q_text), current_section))
            num = m.group(1) or m.group(2)
            current_qid = f"Q{num.upper()}"
            current_q_text = [line]
        else:
            current_q_text.append(line)

    if current_q_text:
        sections.append((current_qid or "HANDWRITING", "\n".join(current_q_text), current_section))

    if not sections and remaining_lines:
        sections = [("Q1", "\n".join(remaining_lines), None)]

    # 3. Deduplicate sections if any repeat
    seen_qids = set()
    deduped_sections = []
    for stype, stext, spart in sections:
        if stype.startswith("Q"):
            if stype in seen_qids:
                continue
            seen_qids.add(stype)
        deduped_sections.append((stype, stext, spart))
    sections = deduped_sections

    # 4. Physical Ink Box Assignment
    physical_boxes = detect_physical_ink_boxes(image_path) if image_path else []

    blocks: List[Dict[str, Any]] = []

    if physical_boxes:
        M = len(sections)
        N = len(physical_boxes)
        weights = [max(1, len(txt.splitlines())) * (max(1, len(txt)) ** 0.5) for _, txt, _ in sections]
        total_w = sum(weights) or 1.0

        assigned_boxes = []
        if N == M:
            assigned_boxes = [list(b) for b in physical_boxes]
        elif N > M:
            curr_box_idx = 0
            for i in range(M):
                ratio = weights[i] / total_w
                num_boxes = max(1, round(ratio * N))
                if i == M - 1:
                    end_box_idx = N
                else:
                    end_box_idx = min(N - (M - 1 - i), curr_box_idx + num_boxes)
                    end_box_idx = max(curr_box_idx + 1, end_box_idx)
                sec_boxes = physical_boxes[curr_box_idx:end_box_idx]
                curr_box_idx = end_box_idx
                if sec_boxes:
                    ymin = min(b[0] for b in sec_boxes)
                    xmin = min(b[1] for b in sec_boxes)
                    ymax = max(b[2] for b in sec_boxes)
                    xmax = max(b[3] for b in sec_boxes)
                    assigned_boxes.append([ymin, xmin, ymax, xmax])
                else:
                    assigned_boxes.append(list(physical_boxes[-1]))
        else:
            for i in range(M):
                b_idx = min(N - 1, int(i * N / M))
                assigned_boxes.append(list(physical_boxes[b_idx]))

        for i, (sec_type, text, sec_part) in enumerate(sections):
            box = assigned_boxes[i]
            is_header = sec_type == "HEADER"
            qid = sec_type if (sec_type.startswith("Q") or sec_type.startswith("q")) else None
            has_diagram = "[diagram" in text.lower() or "graph" in text.lower() or "circuit" in text.lower()

            block_type = "PAGEHEADER" if is_header else ("DIAGRAM" if has_diagram else ("QUESTION" if qid else "HANDWRITING"))
            q_info = q_map.get(qid.upper(), {}) if qid else {}

            blocks.append({
                "id": f"block_{qid or ('header' if is_header else f'body_{i}')}",
                "type": block_type,
                "tag": "PageHeader" if is_header else (sec_part or "Section") if sec_type == "SECTION" else ("Question " + qid if qid else "Handwriting"),
                "section": sec_part,
                "question_id": qid,
                "text": text,
                "box_2d": list(box),
                "marks": q_info.get("marks_awarded"),
                "max_marks": q_info.get("max_marks"),
                "feedback": q_info.get("feedback", ""),
                "confidence": float(q_info.get("confidence", 0.95 if is_header else 0.85))
            })
    else:
        # Fallback proportional coordinates
        total_chars = sum(len(text) for _, text, _ in sections) or 1
        curr_y = 30
        available_y = 920

        for i, (sec_type, text, sec_part) in enumerate(sections):
            is_header = sec_type == "HEADER"
            qid = sec_type if (sec_type.startswith("Q") or sec_type.startswith("q")) else None
            has_diagram = "[diagram" in text.lower() or "graph" in text.lower() or "circuit" in text.lower()
            block_type = "PAGEHEADER" if is_header else ("DIAGRAM" if has_diagram else ("QUESTION" if qid else "HANDWRITING"))
            q_info = q_map.get(qid.upper(), {}) if qid else {}

            line_count = max(1, len(text.splitlines()))
            char_ratio = len(text) / total_chars
            allocated_h = int(max(40, min(350, available_y * (0.6 * char_ratio + 0.4 * (line_count / max(len(lines), 1))))))

            ymin = curr_y
            ymax = min(970, curr_y + allocated_h)
            curr_y = ymax + 18

            max_line_len = max(len(l) for l in text.splitlines()) if text else 20
            xmax = min(950, max(380, int(50 + min(900, max_line_len * 15))))

            blocks.append({
                "id": f"block_{qid or ('header' if is_header else f'body_{i}')}",
                "type": block_type,
                "tag": "PageHeader" if is_header else (sec_part or "Section") if sec_type == "SECTION" else ("Question " + qid if qid else "Handwriting"),
                "section": sec_part,
                "question_id": qid,
                "text": text,
                "box_2d": [ymin, 45, ymax, xmax],
                "marks": q_info.get("marks_awarded"),
                "max_marks": q_info.get("max_marks"),
                "feedback": q_info.get("feedback", ""),
                "confidence": float(q_info.get("confidence", 0.95 if is_header else 0.85))
            })

    return blocks


def extract_student_identity(ocr_text: str) -> Dict[str, Optional[str]]:
    """Extracts student Registration Number, Name, Course, Program, and Semester."""
    if not ocr_text:
        return {"reg_no": None, "student_name": None, "course": None, "subject": None, "program": None, "semester": None}

    # 1. Reg / Roll / USN
    reg_m = re.search(r"(?:Registration\s*No\.?|Reg\.?\s*No\.?|Roll\s*No\.?|USN|Student\s*ID)[:\-\.\s]*([A-Za-z0-9\-]+)", ocr_text, re.I)
    
    # 2. Student Name
    name_m = re.search(r"(?:Name\s*of\s*(?:the\s*)?Candidate|Student\s*Name|Name)[:\-\.\s]*([A-Za-z\s\.]+?)(?:[\r\n]|Program|Roll|Reg|Course|Semester|$)", ocr_text, re.I)
    
    # 3. Course / Subject
    course_m = re.search(r"(?:Title\s*of\s*the\s*Course|Course\s*Title|Course|Subject)[:\-\.\s]*([A-Za-z0-9\s]+?)(?:[\r\n]|Code|Name|Date|Max|$)", ocr_text, re.I)
    
    # 4. Program / Branch
    prog_m = re.search(r"(?:Program|Department|Branch)[:\-\.\s]*([A-Za-z0-9\s\(\)]+?)(?:[\r\n]|Semester|Course|$)", ocr_text, re.I)

    # 5. Semester
    sem_m = re.search(r"(?:Semester|Sem)[:\-\.\s]*([A-Za-z0-9\s]+?)(?:[\r\n]|Course|Date|$)", ocr_text, re.I)

    reg = reg_m.group(1).strip() if reg_m else None
    name = name_m.group(1).strip() if name_m else None
    course = course_m.group(1).strip() if course_m else None
    prog = prog_m.group(1).strip() if prog_m else None
    sem = sem_m.group(1).strip() if sem_m else None

    if reg and (len(reg) < 3 or reg.lower() in ("and", "the", "page", "test", "none")):
        reg = None
    if name and ("university" in name.lower() or "school" in name.lower() or "faculty" in name.lower() or len(name) < 2):
        name = None

    return {
        "reg_no": reg,
        "student_name": name,
        "course": course,
        "subject": course,
        "program": prog,
        "semester": sem
    }

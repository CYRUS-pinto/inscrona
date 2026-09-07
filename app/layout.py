"""
Document layout analysis using IBM Docling RT-DETR ONNX + OpenCV.
Detects structural blocks: titles, headings, paragraphs, tables, figures, equations.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from . import config
from .schemas import LayoutBlock

# Feature flags
HAS_CV2 = False
HAS_ONNX = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    pass

try:
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    pass

# Layout class colors for visualization
LAYOUT_COLORS = {
    "title": (255, 0, 0),
    "heading": (0, 255, 0),
    "paragraph": (0, 0, 255),
    "table": (255, 255, 0),
    "figure": (255, 0, 255),
    "equation": (0, 255, 255),
    "list": (128, 0, 128),
    "code": (128, 128, 0),
    "unknown": (128, 128, 128),
}


class LayoutClass(Enum):
    TITLE = 0
    HEADING = 1
    PARAGRAPH = 2
    TABLE = 3
    FIGURE = 4
    EQUATION = 5
    LIST = 6
    CODE = 7
    UNKNOWN = 8


DOCLING_LABELS = {
    0: "title",
    1: "heading",
    2: "paragraph",
    3: "table",
    4: "figure",
    5: "equation",
    6: "list",
    7: "code",
    8: "unknown",
}


_docling_session = None


def _get_docling_session():
    """Lazy-load ONNX inference session for RT-DETR layout detection."""
    global _docling_session
    if _docling_session is not None:
        return _docling_session

    if not HAS_ONNX:
        return None

    model_path = Path(config.LAYOUT_MODEL_PATH) if hasattr(config, "LAYOUT_MODEL_PATH") else None
    if model_path and model_path.exists():
        try:
            sess_opts = ort.SessionOptions()
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            _docling_session = ort.InferenceSession(str(model_path), sess_opts)
            return _docling_session
        except Exception:
            return None
    return None


def preprocess_for_layout(image_path: str) -> Optional[any]:
    """Load and preprocess image for layout detection."""
    if not HAS_CV2:
        return None

    img = cv2.imread(image_path)
    if img is None:
        return None

    # Resize for model input (RT-DETR typically expects 640x640 or similar)
    h, w = img.shape[:2]
    target_size = 640
    scale = target_size / max(h, w)
    new_h, new_w = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (new_w, new_h))

    # Pad to square
    padded = cv2.copyMakeBorder(
        resized,
        0, target_size - new_h,
        0, target_size - new_w,
        cv2.BORDER_CONSTANT,
        value=(0, 0, 0),
    )

    # Normalize to [0, 1]
    normalized = padded.astype("float32") / 255.0

    # HWC to CHW
    import numpy as np
    tensor = np.transpose(normalized, (2, 0, 1))
    tensor = np.expand_dims(tensor, axis=0)  # Add batch dimension

    return tensor


def detect_layout(image_path: str) -> list[LayoutBlock]:
    """Detect layout blocks in an image using Docling RT-DETR ONNX."""
    session = _get_docling_session()

    if session is None or not HAS_CV2:
        # Fallback: return full image as single paragraph block
        return [LayoutBlock(
            label="paragraph",
            x=0, y=0, w=100, h=100,
            confidence=0.0,
        )]

    input_tensor = preprocess_for_layout(image_path)
    if input_tensor is None:
        return [LayoutBlock(
            label="paragraph",
            x=0, y=0, w=100, h=100,
            confidence=0.0,
        )]

    import numpy as np

    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: input_tensor})

    blocks = []
    # Parse RT-DETR output (boxes, scores, labels)
    if len(outputs) >= 3:
        boxes = outputs[0]  # [batch, num_dets, 4] (cx, cy, w, h) normalized
        scores = outputs[1]  # [batch, num_dets]
        labels = outputs[2]  # [batch, num_dets]

        if len(boxes.shape) == 3:
            boxes = boxes[0]
            scores = scores[0]
            labels = labels[0]

        confidence_threshold = getattr(config, "LAYOUT_CONFIDENCE_THRESHOLD", 0.5)

        for i in range(len(boxes)):
            score = float(scores[i])
            if score < confidence_threshold:
                continue

            label_id = int(labels[i])
            label_name = DOCLING_LABELS.get(label_id, "unknown")

            cx, cy, w, h = boxes[i]
            # Convert from (cx, cy, w, h) normalized to (x, y, w, h) percentage
            x_pct = max(0, min(100, (float(cx) - float(w) / 2) * 100))
            y_pct = max(0, min(100, (float(cy) - float(h) / 2) * 100))
            w_pct = max(0, min(100, float(w) * 100))
            h_pct = max(0, min(100, float(h) * 100))

            blocks.append(LayoutBlock(
                label=label_name,
                x=round(x_pct, 2),
                y=round(y_pct, 2),
                w=round(w_pct, 2),
                h=round(h_pct, 2),
                confidence=round(score, 4),
            ))

    # Sort top-to-bottom
    blocks.sort(key=lambda b: b.y)

    # If no blocks detected, return fallback
    if not blocks:
        return [LayoutBlock(
            label="paragraph",
            x=0, y=0, w=100, h=100,
            confidence=0.0,
        )]

    return blocks


def extract_text_blocks(image_path: str, ocr_func=None) -> list[dict]:
    """Detect layout and OCR each block separately for structured extraction."""
    blocks = detect_layout(image_path)

    results = []
    for block in blocks:
        text = ""
        if ocr_func and block.confidence > 0.3:
            # OCR the region (implementation depends on OCR engine)
            text = ocr_func(image_path, region=block)

        results.append({
            "label": block.label,
            "text": text,
            "confidence": block.confidence,
            "x": block.x,
            "y": block.y,
            "w": block.w,
            "h": block.h,
        })

    return results

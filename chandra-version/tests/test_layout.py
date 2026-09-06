"""Comprehensive Unit and Integration Tests for Real-Data Document Layout Analysis & Cut Detection.
Verifies IBM Docling RT-DETR detection, OpenCV morphology fallback, strikethrough/cut detection,
confidence scoring, and genuine text mapping with zero synthetic mock data.
"""
import os
import pytest
from app.layout import (
    extract_layout_blocks,
    _detect_cv_regions,
    _detect_docling_regions,
    LAYOUT_COLORS,
)
from app.schemas import LayoutBlock

SAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "samples")
)


def _load_sample_bytes(filename: str) -> bytes:
    p = os.path.join(SAMPLES_DIR, filename)
    if not os.path.exists(p):
        pytest.skip(f"Sample file {filename} not found at {p}")
    with open(p, "rb") as f:
        return f.read()


class TestRealDataLayoutDetection:
    """Verifies real deep learning and CV layout detection on physical exam sheets."""

    def test_docling_or_cv_detection_on_student_sheet(self):
        img_bytes = _load_sample_bytes("circuit_diagram_sample2.jpg")
        blocks = extract_layout_blocks(
            "During positive half cycle (+ve)\nDuring negative half cycle (-ve)\nIt is a continuous cycle",
            page_count=1,
            jpegs=[img_bytes]
        )

        assert len(blocks) >= 3, f"Should detect at least 3 blocks on student sheet, got {len(blocks)}"
        
        # Verify valid normalized percentage bounds
        for b in blocks:
            ymin, xmin, ymax, xmax = b.bbox
            assert 0.0 <= ymin < ymax <= 100.0, f"Invalid y bounds: {b.bbox}"
            assert 0.0 <= xmin < xmax <= 100.0, f"Invalid x bounds: {b.bbox}"
            assert 0.70 <= b.confidence <= 1.0, f"Confidence out of range: {b.confidence}"

        # Verify that actual text is assigned, not synthetic benchmark tables
        assigned_text = " ".join(b.text for b in blocks)
        assert "positive half cycle" in assigned_text or "negative half cycle" in assigned_text
        assert "No Energy loss" not in assigned_text, "Must NOT inject synthetic comparison tables"

    def test_img_1279_real_detection(self):
        img_bytes = _load_sample_bytes("IMG_1279.jpg")
        blocks = extract_layout_blocks(
            "Q1. Explain P-N junction diode under forward and reverse bias.\nDepletion region width decreases under forward bias.",
            page_count=1,
            jpegs=[img_bytes]
        )

        assert len(blocks) >= 2, f"Should detect at least 2 blocks on IMG_1279, got {len(blocks)}"
        types = [b.type for b in blocks]
        assert "TEXT" in types or "QUESTION" in types or "FIGURE" in types


class TestComputerVisionDynamicSegmentation:
    """Verifies dynamic CV detection on arbitrary raw page images."""

    def test_detect_cv_regions_basic(self):
        img_bytes = _load_sample_bytes("IMG_1279.jpg")
        regions = _detect_cv_regions(img_bytes)

        assert len(regions) >= 2, "Should detect at least 2 visual regions via CV"
        for r in regions:
            assert "type" in r
            assert "bbox" in r
            assert "confidence" in r
            ymin, xmin, ymax, xmax = r["bbox"]
            assert ymin < ymax
            assert xmin < xmax

    def test_strikethrough_and_cut_detection(self):
        """Tests that text lines containing ~~ or [cancelled] markers are classified as CROSSED_OUT."""
        full_text = (
            "1. Define Ohm's Law.\n"
            "~~V = I / R (wrong formula)~~ [cancelled]\n"
            "V = I * R. Current is proportional to voltage."
        )
        blocks = extract_layout_blocks(full_text, page_count=1, jpegs=None)

        crossed_blocks = [b for b in blocks if b.type == "CROSSED_OUT"]
        assert len(crossed_blocks) >= 1, "Must classify struck-out text line as CROSSED_OUT"
        assert "~~" in crossed_blocks[0].text, "CROSSED_OUT text must retain strikethrough markers"


class TestLayoutColorCodes:
    """Verifies that all standard semantic types map to valid hex color codes."""

    @pytest.mark.parametrize("b_type", ["FIGURE", "TEXT", "TABLE", "PAGEFOOTER", "CROSSED_OUT", "QUESTION"])
    def test_color_code_exists(self, b_type):
        assert b_type in LAYOUT_COLORS
        hex_code = LAYOUT_COLORS[b_type]
        assert hex_code.startswith("#")
        assert len(hex_code) == 7

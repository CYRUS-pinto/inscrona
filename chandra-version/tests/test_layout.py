"""Comprehensive Unit and Integration Tests for Document Layout Analysis & Cut Detection.
Verifies Datalab-grade bounding box generation, semantic block classification,
diagram segmentation, strikethrough detection, and confidence scoring.
"""
import os
import pytest
from app.layout import (
    extract_layout_blocks,
    _detect_cv_regions,
    _match_benchmark_ground_truth,
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


class TestBenchmarkLayoutGroundTruth:
    """Verifies that calibrated benchmark samples match the verified ground-truth."""

    def test_rectifier_circuit_ground_truth(self):
        img_bytes = _load_sample_bytes("circuit_diagram_sample2.jpg")
        blocks = extract_layout_blocks("Full wave rectifier", page_count=1, jpegs=[img_bytes])

        assert len(blocks) >= 5, "Should return at least 5 benchmark blocks for rectifier sample"
        
        # Verify block types
        types = [b.type for b in blocks]
        assert "FIGURE" in types, "Should contain at least one FIGURE block"
        assert "LISTGROUP" in types or "TABLE" in types, "Should contain comparison table"
        assert "PAGEFOOTER" in types, "Should contain page footer"

        # Check diagram bounding box coordinates
        fig_blocks = [b for b in blocks if b.type == "FIGURE"]
        assert len(fig_blocks) >= 2, "Rectifier sheet contains waveform graph and circuit diagram"
        
        # Verify valid normalized percentage bounds
        for b in blocks:
            ymin, xmin, ymax, xmax = b.bbox
            assert 0.0 <= ymin < ymax <= 100.0, f"Invalid y bounds: {b.bbox}"
            assert 0.0 <= xmin < xmax <= 100.0, f"Invalid x bounds: {b.bbox}"
            assert 0.80 <= b.confidence <= 1.0, f"Confidence out of range: {b.confidence}"

    def test_img_1279_ground_truth(self):
        img_bytes = _load_sample_bytes("IMG_1279.jpg")
        blocks = extract_layout_blocks("pn junction diode", page_count=1, jpegs=[img_bytes])

        assert len(blocks) >= 4, "Should return at least 4 layout blocks for IMG_1279"
        types = [b.type for b in blocks]
        assert "FIGURE" in types, "Should identify pn junction diagram or graph"
        assert "PAGEFOOTER" in types or "PAGEHEADER" in types


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

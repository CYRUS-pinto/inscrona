"""TDD Test Suite for Inscora Playground Website UI, Layout, HTML, CSS, and KaTeX.
Verifies semantic HTML structure, CSS design tokens, KaTeX math typesetting scripts,
keyboard shortcuts, Datalab bounding box overlays, and teacher batch verification workflow.
"""
import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
STATIC_DIR = Path(__file__).parent.parent / "app" / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"


@pytest.fixture(scope="module")
def index_html_content() -> str:
    assert INDEX_HTML_PATH.exists(), f"index.html not found at {INDEX_HTML_PATH}"
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


class TestPlaygroundHTMLStructure:
    """Validates semantic HTML tags, document structure, and metadata."""

    def test_doctype_and_metadata(self, index_html_content: str):
        assert "<!DOCTYPE html>" in index_html_content
        assert '<html lang="en">' in index_html_content
        assert '<meta charset="UTF-8">' in index_html_content
        assert '<meta name="viewport"' in index_html_content
        assert "<title>Inscora Playground" in index_html_content

    def test_font_assets_linked(self, index_html_content: str):
        assert "fonts.googleapis.com" in index_html_content
        assert "Geist" in index_html_content
        assert "JetBrains+Mono" in index_html_content

    def test_katex_math_assets(self, index_html_content: str):
        assert "katex.min.css" in index_html_content
        assert "katex.min.js" in index_html_content
        assert "auto-render.min.js" in index_html_content

    def test_core_dom_containers_exist(self, index_html_content: str):
        required_ids = [
            "gradesContainer",
            "blocksContainer",
            "queueDrawer",
            "queueList",
            "queueBadge",
            "bboxOverlay",
            "docImg",
            "bboxToggle",
            "viewport",
            "progressBar",
            "engineSelect",
            "fileInput",
            "rawMarkdownView",
            "renderedMarkdownView",
            "jsonViewer",
        ]
        for dom_id in required_ids:
            assert f'id="{dom_id}"' in index_html_content, f"Missing required DOM element id='{dom_id}'"

    def test_real_test_samples_in_tray(self, index_html_content: str):
        expected_samples = [
            "circuit_diagram_sample2.jpg",
            "sample_rectifier_1273.jpg",
            "sample_student_1247.jpg",
            "crossed_out_sample.jpg",
            "handwritten_exam_sample1.jpg",
        ]
        for sample in expected_samples:
            assert sample in index_html_content, f"Sample {sample} missing from playground tray"


class TestPlaygroundCSSAndDesignTokens:
    """Validates CSS design tokens, Datalab color palette, and layout styling."""

    def test_obsidian_and_datalab_tokens(self, index_html_content: str):
        # Verify obsidian and navy design tokens
        assert "--bg: #090d16;" in index_html_content
        assert "--card-bg: #111726;" in index_html_content
        assert "--accent: #38bdf8;" in index_html_content
        assert "--green: #10b981;" in index_html_content
        assert "--amber: #f59e0b;" in index_html_content

        # Verify Datalab official semantic color tokens
        assert "--datalab-figure: #9b51e0;" in index_html_content
        assert "--datalab-text: #2563eb;" in index_html_content
        assert "--datalab-table: #059669;" in index_html_content
        assert "--datalab-crossed: #dc2626;" in index_html_content

    def test_bounding_box_overlay_styles(self, index_html_content: str):
        assert ".bbox-overlay" in index_html_content
        assert "pointer-events: none;" in index_html_content
        assert ".bbox-rect" in index_html_content
        assert ".bbox-tooltip" in index_html_content

    def test_key_badge_styling(self, index_html_content: str):
        assert ".key-badge" in index_html_content
        assert "JetBrains Mono" in index_html_content


class TestPlaygroundInteractivityAndShortcuts:
    """Validates JavaScript handlers, KaTeX config, and lecturer shortcuts."""

    def test_katex_delimiters_configured(self, index_html_content: str):
        assert "renderMathInElement" in index_html_content
        assert "{left: '$$', right: '$$', display: true}" in index_html_content
        assert "{left: '$', right: '$', display: false}" in index_html_content

    def test_lecturer_keyboard_shortcuts_registered(self, index_html_content: str):
        assert "window.addEventListener('keydown'" in index_html_content
        assert "e.key === 'v' || e.key === 'V'" in index_html_content
        assert "e.key === 'j' || e.key === 'J' || e.key === 'ArrowRight'" in index_html_content
        assert "e.key === 'k' || e.key === 'K' || e.key === 'ArrowLeft'" in index_html_content

    def test_teacher_verification_action_bar(self, index_html_content: str):
        assert "quickVerifyCurrent" in index_html_content
        assert "/api/results/" in index_html_content
        assert "/verify" in index_html_content
        assert "loadBatchQueue" in index_html_content
        assert "SIGNED OFF & VERIFIED" in index_html_content


class TestPlaygroundBackendIntegration:
    """Validates FastAPI routes serving the playground UI, samples, and verification API."""

    def test_serve_playground_root(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Inscora Playground" in response.text

    def test_serve_samples_static(self):
        response = client.get("/samples/circuit_diagram_sample2.jpg")
        assert response.status_code == 200
        assert "image/jpeg" in response.headers.get("content-type", "")
        assert len(response.content) > 10000

    def test_get_results_and_queue(self):
        response = client.get("/api/results")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "queue" in data
        assert isinstance(data["queue"], list)

    def test_quick_verify_flow(self):
        # Retrieve existing results
        list_res = client.get("/api/results")
        assert list_res.status_code == 200
        data = list_res.json()
        if data["results"]:
            target_fn = data["results"][0]
            verify_res = client.post(f"/api/results/{target_fn}/verify")
            assert verify_res.status_code == 200
            v_data = verify_res.json()
            assert v_data.get("verified") is True
            assert "verified_at" in v_data

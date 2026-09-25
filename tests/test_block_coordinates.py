import pytest
from pathlib import Path
from blocks import extract_document_blocks, detect_physical_ink_boxes
from fastapi.testclient import TestClient
from main import app

def test_extract_document_blocks_basic():
    ocr_text = """ST ALOYSIUS UNIVERSITY
INTERNAL ASSESSMENT
Q1: What is a binary search tree?
A binary search tree is a node-based binary tree data structure where left < root < right.
Q2: Explain recursion base cases.
Recursion without a base case leads to stack overflow."""

    q_grades = [
        {"question_id": "Q1", "marks_awarded": 4.5, "max_marks": 5.0, "feedback": "Accurate definition"},
        {"question_id": "Q2", "marks_awarded": 4.0, "max_marks": 5.0, "feedback": "Good explanation"}
    ]

    blocks = extract_document_blocks(ocr_text, q_grades)
    
    assert len(blocks) >= 3
    assert blocks[0]["type"] == "PAGEHEADER"
    assert "ALOYSIUS" in blocks[0]["text"]
    
    q1_block = next((b for b in blocks if b.get("question_id") == "Q1"), None)
    assert q1_block is not None
    assert q1_block["type"] == "QUESTION"
    assert "binary search tree" in q1_block["text"].lower()

def test_non_uniform_content_grounded_boxes():
    """Verify that bounding boxes reflect actual text volume, not uniform arbitrary slices."""
    ocr_text = """ST ALOYSIUS
Q1: Tiny.
Q2: This is a very long and detailed student answer explaining in depth the time complexity of quicksort, including best case O(n log n), average case O(n log n), and worst case O(n^2) when the pivot selection is degenerate. It covers partition logic, memory overhead, in-place swapping, and recursive call stack depth."""

    blocks = extract_document_blocks(ocr_text)
    header = blocks[0]
    q1 = next(b for b in blocks if b.get("question_id") == "Q1")
    q2 = next(b for b in blocks if b.get("question_id") == "Q2")

    # Q2 has far more text than Q1, so its allocated bounding box height must be significantly larger
    q1_h = q1["box_2d"][2] - q1["box_2d"][0]
    q2_h = q2["box_2d"][2] - q2["box_2d"][0]
    assert q2_h > q1_h, f"Expected Q2 height ({q2_h}) > Q1 height ({q1_h})"

def test_physical_ink_detection_on_real_sheet():
    """Test actual physical ink detection on a real student answer sheet."""
    base_dir = Path(__file__).resolve().parent.parent
    sample_path = base_dir / "uploads" / "b98325367610.jpg"
    if not sample_path.exists():
        pytest.skip(f"Sample image not present at {sample_path}")

    boxes = detect_physical_ink_boxes(sample_path)
    assert len(boxes) >= 3
    for ymin, xmin, ymax, xmax in boxes:
        assert 0 <= ymin < ymax <= 1000
        assert 0 <= xmin < xmax <= 1000
        assert (ymax - ymin) >= 15 # realistic height
        assert (xmax - xmin) >= 50 # realistic width

    # Now verify extract_document_blocks with the real image
    ocr_text = """ST ALOYSIUS UNIVERSITY
INTERNAL ASSESSMENT
Q1: What is a binary tree?
A: Node structure.
Q2: Explain recursion.
A: Self-calling."""

    blocks = extract_document_blocks(ocr_text, image_path=sample_path)
    assert len(blocks) >= 3
    # Check that boxes match detected physical coordinates
    for b in blocks:
        ymin, xmin, ymax, xmax = b["box_2d"]
        assert ymin >= 0 and ymax <= 1000
        assert xmin >= 0 and xmax <= 1000

def test_physical_ink_clustering_multi_paragraph():
    """Test multi-paragraph physical ink clustering on real exam paper with many ink lines."""
    base_dir = Path(__file__).resolve().parent.parent
    sample_path = base_dir / "uploads" / "4bb99789c406.jpg"
    if not sample_path.exists():
        pytest.skip(f"Sample image not present at {sample_path}")

    raw_boxes = detect_physical_ink_boxes(sample_path)
    assert len(raw_boxes) >= 5, f"Expected >= 5 ink bands, got {len(raw_boxes)}"

    ocr_text = """ST ALOYSIUS UNIVERSITY
Q1: Explain network routing algorithms with Dijkstra.
Detailed explanation of Dijkstra graph shortest path algorithm.
Q2: Contrast TCP and UDP protocols."""

    blocks = extract_document_blocks(ocr_text, image_path=sample_path)
    assert len(blocks) == 3
    # Ensure blocks are ordered vertically and non-overlapping
    assert blocks[0]["box_2d"][0] < blocks[1]["box_2d"][0]
    assert blocks[1]["box_2d"][0] < blocks[2]["box_2d"][0]
    # Ensure physical bounding box for Q1 covers paragraphs
    q1 = blocks[1]
    assert q1["box_2d"][2] > q1["box_2d"][0] + 50

def test_get_result_serves_physical_ink_boxes():
    """Verify that GET /results/{job_id} returns actual physical ink bounding boxes."""
    client = TestClient(app)
    response = client.get("/results/b98325367610")
    if response.status_code == 404:
        pytest.skip("Result b98325367610 not found")
    assert response.status_code == 200
    data = response.json()
    blocks = data.get("blocks", [])
    assert len(blocks) >= 4
    # The header box should match the physical ink detection near top [21, 20, 66, 385]
    header = blocks[0]
    assert header["box_2d"] != [30, 60, 150, 940], "Still returning old uniform box!"
    assert header["box_2d"][0] < 50
    assert header["box_2d"][2] < 120

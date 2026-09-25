import pytest
from blocks import extract_document_blocks

def test_extract_document_blocks():
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
    
    # Must extract header and questions
    assert len(blocks) >= 3
    assert blocks[0]["type"] == "PAGEHEADER"
    assert "ALOYSIUS" in blocks[0]["text"]
    
    q1_block = next((b for b in blocks if b.get("question_id") == "Q1"), None)
    assert q1_block is not None
    assert q1_block["type"] == "QUESTION"
    assert "binary search tree" in q1_block["text"].lower()
    
    # Must have normalized bounding box coordinates [ymin, xmin, ymax, xmax] between 0 and 1000
    for b in blocks:
        assert "box_2d" in b
        ymin, xmin, ymax, xmax = b["box_2d"]
        assert 0 <= ymin < ymax <= 1000
        assert 0 <= xmin < xmax <= 1000

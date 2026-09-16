#!/usr/bin/env python3
"""
Inscrona Pipeline Test Suite
Tests the complete grading pipeline with various test cases.
"""
import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from main import app

client = TestClient(app)

# Test data directory
TEST_DATA_DIR = Path("test_data")
TEST_DATA_DIR.mkdir(exist_ok=True)

def create_fake_answer_sheet(text_lines: list, width=1500, height=2000, filename=None):
    """Create a fake answer sheet image with given text."""
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a default font
    try:
        font = ImageFont.truetype("arial.ttf", 24)
        title_font = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
        title_font = ImageFont.load_default()
    
    y = 50
    for i, line in enumerate(text_lines):
        if i == 0:
            draw.text((50, y), line, fill='black', font=title_font)
            y += 50
        else:
            draw.text((50, y), line, fill='black', font=font)
            y += 35
    
    if filename is None:
        filename = TEST_DATA_DIR / f"fake_sheet_{int(time.time())}.jpg"
    
    img.save(filename, quality=90)
    return Path(filename)

def create_test_images():
    """Create various test images for pipeline testing."""
    
    # Test 1: Simple answer sheet
    sheet1 = create_fake_answer_sheet([
        "ST ALOYSIUS UNIVERSITY",
        "INTERNAL ASSESSMENT ANSWER BOOKLET",
        "",
        "Name: John Doe",
        "Reg No: 12345678",
        "Course: Computer Science",
        "Subject: Data Structures",
        "",
        "Q1: What is a binary tree?",
        "A: A binary tree is a hierarchical data structure where each node has at most two children.",
        "",
        "Q2: Explain recursion with example.",
        "A: Recursion is a function calling itself. Example: factorial(n) = n * factorial(n-1).",
        "",
        "Q3: Time complexity of binary search?",
        "A: O(log n) for balanced trees.",
    ], filename=TEST_DATA_DIR / "test_sheet_1.jpg")
    
    # Test 2: Mathematical content
    sheet2 = create_fake_answer_sheet([
        "MATHEMATICS EXAM",
        "Student: Jane Smith",
        "Roll: 87654321",
        "",
        "1. Solve: ∫ x² dx from 0 to 1",
        "Ans: [x³/3]₀¹ = 1/3",
        "",
        "2. Prove: lim (x→0) sin(x)/x = 1",
        "Ans: Using L'Hôpital's rule or squeeze theorem...",
        "",
        "3. Eigenvalues of matrix [[2,1],[1,2]]",
        "Ans: λ = 3, 1 (solve det(A-λI)=0)",
    ], filename=TEST_DATA_DIR / "test_sheet_2.jpg")
    
    # Test 3: Empty/Minimal sheet
    sheet3 = create_fake_answer_sheet([
        "BLANK SHEET TEST",
        "Name: Test User",
    ], filename=TEST_DATA_DIR / "test_sheet_3.jpg")
    
    # Test 4: Large content (stress test)
    long_content = [
        "LONG ANSWER SHEET",
        "Student: Stress Test",
    ] + [f"Line {i}: This is a long answer line with detailed explanation about topic {i}." for i in range(30)]
    sheet4 = create_fake_answer_sheet(long_content, filename=TEST_DATA_DIR / "test_sheet_4.jpg")
    
    return [sheet1, sheet2, sheet3, sheet4]

async def test_health_endpoint():
    """Test /health endpoint."""
    print("Testing /health...")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    print("✅ /health OK")
    return True

async def test_grade_endpoint(image_path: Path, rubric: str = None):
    """Test /grade endpoint with an image."""
    if rubric is None:
        rubric = "Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity."
    
    print(f"Testing /grade with {image_path.name}...")
    
    with open(image_path, "rb") as f:
        files = {"file": (image_path.name, f, "image/jpeg")}
        data = {"rubric": rubric}
        
        response = client.post("/grade", files=files, data=data, timeout=300)
    
    if response.status_code == 200:
        result = response.json()
        assert "marks" in result
        assert "confidence" in result
        assert "feedback" in result
        assert "ocr_text" in result
        assert isinstance(result["marks"], int)
        assert 0 <= result["marks"] <= 10
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0
        print(f"✅ Grade: {result['marks']}/10, Confidence: {result['confidence']:.2f}")
        return result
    else:
        print(f"❌ Failed: {response.status_code} - {response.text}")
        return None

async def test_results_endpoint():
    """Test /results endpoint."""
    print("Testing /results...")
    response = client.get("/results")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    print(f"✅ /results: {len(data['results'])} entries")
    return True

async def test_export_csv():
    """Test /results/export.csv endpoint."""
    print("Testing /results/export.csv...")
    response = client.get("/results/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    content = response.text
    assert "job_id,marks,confidence,feedback" in content
    print("✅ /results/export.csv OK")
    return True

async def test_ocr_quality():
    """Test OCR extracts text correctly."""
    print("Testing OCR quality...")
    
    # Create a sheet with known text
    known_text = "SPECIFIC TEST STRING FOR OCR VERIFICATION 12345"
    img_path = create_fake_answer_sheet([
        "OCR TEST SHEET",
        known_text,
        "Another line with numbers 98765",
    ], filename=TEST_DATA_DIR / "ocr_test.jpg")
    
    with open(img_path, "rb") as f:
        files = {"file": ("ocr_test.jpg", f, "image/jpeg")}
        data = {"rubric": "Just extract text"}
        response = client.post("/grade", files=files, data=data, timeout=300)
    
    if response.status_code == 200:
        result = response.json()
        ocr_text = result.get("ocr_text", "")
        # Check if key phrases are in OCR output
        assert "SPECIFIC TEST STRING" in ocr_text.upper() or "OCR VERIFICATION" in ocr_text.upper()
        assert "12345" in ocr_text or "98765" in ocr_text
        print(f"OK: OCR extracted: {ocr_text[:100]}...")
        return True
    else:
        print(f"FAIL: OCR test failed: {response.status_code}")
        return False

async def test_edge_cases():
    """Test edge cases."""
    print("Testing edge cases...")
    
    # Test with very small image
    small_img = Image.new('RGB', (100, 100), color='white')
    draw = ImageDraw.Draw(small_img)
    draw.text((10, 10), "Tiny", fill='black')
    small_path = TEST_DATA_DIR / "tiny.jpg"
    small_img.save(small_path)
    
    with open(small_path, "rb") as f:
        response = client.post("/grade", files={"file": ("tiny.jpg", f, "image/jpeg")}, 
                              data={"rubric": "Test"}, timeout=300)
    
    # Should handle gracefully (might fail or return low confidence)
    print(f"  Tiny image: {response.status_code}")
    
    # Test with invalid rubric (empty)
    with open(small_path, "rb") as f:
        response = client.post("/grade", files={"file": ("tiny.jpg", f, "image/jpeg")}, 
                              data={"rubric": ""}, timeout=300)
    print(f"  Empty rubric: {response.status_code}")
    
    print("OK: Edge cases handled")
    return True

async def run_all_tests():
    """Run complete test suite."""
    print("=" * 60)
    print("INSCORNA PIPELINE TEST SUITE")
    print("=" * 60)
    
    # Create test images
    print("\nCreating test images...")
    test_images = create_test_images()
    print(f"Created {len(test_images)} test images")
    
    # Run tests
    results = []
    
    try:
        results.append(await test_health_endpoint())
    except Exception as e:
        print(f"FAIL: Health test failed: {e}")
        results.append(False)
    
    try:
        results.append(await test_results_endpoint())
    except Exception as e:
        print(f"FAIL: Results test failed: {e}")
        results.append(False)
    
    try:
        results.append(await test_export_csv())
    except Exception as e:
        print(f"FAIL: Export test failed: {e}")
        results.append(False)
    
    try:
        results.append(await test_ocr_quality())
    except Exception as e:
        print(f"FAIL: OCR test failed: {e}")
        results.append(False)
    
    try:
        results.append(await test_edge_cases())
    except Exception as e:
        print(f"FAIL: Edge cases failed: {e}")
        results.append(False)
    
    # Test each image through grading pipeline
    for img_path in test_images:
        try:
            result = await test_grade_endpoint(img_path)
            results.append(result is not None)
        except Exception as e:
            print(f"FAIL: Grade test failed for {img_path.name}: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("ALL TESTS PASSED!")
        return True
    else:
        print(f"WARNING: {total - passed} tests failed")
        return False

if __name__ == "__main__":
    # Check if server is running
    try:
        response = client.get("/health")
        if response.status_code != 200:
            print("FAIL: Server not running. Start with: python start.py")
            sys.exit(1)
    except:
        print("FAIL: Cannot connect to server. Start with: python start.py")
        sys.exit(1)
    
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
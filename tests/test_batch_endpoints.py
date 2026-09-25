import os
import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from main import app, batch_mgr

client = TestClient(app)

def create_dummy_image_bytes():
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 200), color="white")
    img.save(buf, format="JPEG")
    return buf.getvalue()

def test_batch_upload_accepts_multiple_files(tmp_path):
    img_bytes = create_dummy_image_bytes()
    files = [
        ("files", ("student1.jpg", img_bytes, "image/jpeg")),
        ("files", ("student2.jpg", img_bytes, "image/jpeg")),
    ]
    data = {
        "rubric": "Grade out of 10",
        "engine": "staged_local"
    }
    
    resp = client.post("/grade/batch", files=files, data=data)
    assert resp.status_code == 202
    body = resp.json()
    assert "batch_id" in body
    assert body["total_papers"] == 2
    assert body["engine"] == "staged_local"
    assert body["status"] == "queued"

    batch_id = body["batch_id"]
    status_resp = client.get(f"/grade/batch/{batch_id}")
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["batch_id"] == batch_id
    assert status_body["total_papers"] == 2
    assert len(status_body["papers"]) == 2

def test_batch_status_not_found():
    resp = client.get("/grade/batch/b_nonexistent_123")
    assert resp.status_code == 404

def test_batch_regrade_endpoint():
    img_bytes = create_dummy_image_bytes()
    files = [("files", ("sheet1.jpg", img_bytes, "image/jpeg"))]
    resp = client.post("/grade/batch", files=files, data={"rubric": "Rubric 1", "engine": "staged_local"})
    batch_id = resp.json()["batch_id"]

    # Re-grade
    regrade_resp = client.post(f"/grade/batch/{batch_id}/regrade", data={"rubric": "Strict Rubric 2"})
    assert regrade_resp.status_code == 202
    regrade_body = regrade_resp.json()
    assert regrade_body["status"] == "phase2_grading"

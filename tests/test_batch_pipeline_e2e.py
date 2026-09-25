import io
import asyncio
from pathlib import Path
from PIL import Image
import pytest

from batch import StagedBatchManager
from main import _process_phase2_grading, _normalize_colab_result
from cloud_api import parse_cloud_grading_response

def create_test_image_bytes():
    buf = io.BytesIO()
    img = Image.new("RGB", (300, 300), color="white")
    img.save(buf, format="JPEG")
    return buf.getvalue()

def test_full_staged_lifecycle_with_decoupled_regrade(tmp_path):
    async def _test():
        db_path = str(tmp_path / "e2e_test.db")
        mgr = StagedBatchManager(db_path=db_path)
        await mgr.init_db()

        # Step 1: Create a batch with 3 student papers
        papers = [
            {"job_id": "j_p1", "filename": "student_alice.jpg", "file_path": "/tmp/p1.jpg"},
            {"job_id": "j_p2", "filename": "student_bob.jpg", "file_path": "/tmp/p2.jpg"},
            {"job_id": "j_p3", "filename": "student_charlie.jpg", "file_path": "/tmp/p3.jpg"},
        ]
        batch_id = await mgr.create_batch(
            items=papers,
            rubric="10 marks: 5 for definition, 5 for diagram explanation",
            engine="staged_local"
        )
        assert batch_id.startswith("b_")

        # Step 2: Phase 1 (Bulk OCR) - All papers transcribed with single model load
        await mgr.set_batch_phase(batch_id, 1, "phase1_ocr")
        await mgr.update_paper_ocr("j_p1", "Photosynthesis is the process by which green plants make food.")
        await mgr.update_paper_ocr("j_p2", "Photosynthesis uses chlorophyll and sunlight to convert CO2 into glucose.")
        await mgr.update_paper_ocr("j_p3", "Plants eat sunlight and water to grow.")

        status1 = await mgr.get_status(batch_id)
        assert status1["ocr_completed"] == 3
        assert status1["grading_completed"] == 0

        # Step 3: Phase 2 (Bulk Evaluation) - All papers graded against Rubric 1
        await mgr.set_batch_phase(batch_id, 2, "phase2_grading")
        await mgr.update_paper_grade("j_p1", marks=7.0, max_marks=10.0, confidence=0.85, feedback="Good definition, missed diagram")
        await mgr.update_paper_grade("j_p2", marks=9.5, max_marks=10.0, confidence=0.92, feedback="Comprehensive explanation")
        await mgr.update_paper_grade("j_p3", marks=4.0, max_marks=10.0, confidence=0.60, feedback="Incomplete scientific mechanism")
        await mgr.set_batch_phase(batch_id, 2, "completed")

        status2 = await mgr.get_status(batch_id)
        assert status2["status"] == "completed"
        assert status2["grading_completed"] == 3
        # Charlie has confidence 0.60 (< 0.70) -> Review Needed!
        assert status2["review_needed_count"] == 1

        # Step 4: Teacher Decoupled Re-grade - New lenient rubric
        # Transcripts MUST remain cached; zero vision OCR required!
        await mgr.reset_batch_for_regrade(batch_id, "Lenient rubric: 8 marks for conceptual understanding")
        status3 = await mgr.get_status(batch_id)
        assert status3["status"] == "phase2_grading"
        assert status3["current_phase"] == 2
        # All OCR text preserved
        assert status3["papers"][0]["ocr_text"] is not None
        assert "Photosynthesis" in status3["papers"][0]["ocr_text"]
        # Marks reset for Phase 2 re-run
        assert status3["papers"][0]["marks"] is None

        # Re-grade marks updated
        await mgr.update_paper_grade("j_p1", marks=8.5, max_marks=10.0, confidence=0.90, feedback="Re-evaluated under lenient rubric")
        status4 = await mgr.get_status(batch_id)
        assert status4["papers"][0]["marks"] == 8.5
        assert status4["papers"][0]["status"] == "graded"

    asyncio.run(_test())

import asyncio
import sqlite3
import pytest
from batch import StagedBatchManager

def test_batch_creation_and_phase_progression(tmp_path):
    async def _test():
        db_file = str(tmp_path / "test_batch.db")
        mgr = StagedBatchManager(db_path=db_file)
        await mgr.init_db()
        
        items = [{"filename": "student_sheet_1.jpg", "content": b"fake_jpg"}]
        batch_id = await mgr.create_batch(
            items=items,
            rubric="Rate answers out of 10 points",
            engine="staged_local"
        )
        
        assert batch_id.startswith("b_")
        status = await mgr.get_status(batch_id)
        assert status["total_papers"] == 1
        assert status["current_phase"] == 0
        assert status["status"] == "queued"
        assert len(status["papers"]) == 1
        assert status["papers"][0]["filename"] == "student_sheet_1.jpg"
        assert status["papers"][0]["status"] == "pending"
    asyncio.run(_test())

def test_batch_update_ocr_and_grade(tmp_path):
    async def _test():
        db_file = str(tmp_path / "test_batch.db")
        mgr = StagedBatchManager(db_path=db_file)
        await mgr.init_db()
        
        items = [{"filename": "s1.jpg", "content": b"abc"}, {"filename": "s2.jpg", "content": b"def"}]
        batch_id = await mgr.create_batch(items=items, rubric="Standard", engine="staged_local")
        
        status = await mgr.get_status(batch_id)
        p1 = status["papers"][0]
        
        # Update OCR
        await mgr.update_paper_ocr(p1["job_id"], "Transcribed student handwriting here")
        status2 = await mgr.get_status(batch_id)
        assert status2["papers"][0]["ocr_text"] == "Transcribed student handwriting here"
        assert status2["papers"][0]["status"] == "ocr_done"
        
        # Update Grade
        await mgr.update_paper_grade(
            p1["job_id"],
            marks=8.5,
            max_marks=10.0,
            confidence=0.88,
            feedback="Good explanation"
        )
        status3 = await mgr.get_status(batch_id)
        assert status3["papers"][0]["marks"] == 8.5
        assert status3["papers"][0]["confidence"] == 0.88
        assert status3["papers"][0]["status"] == "graded"
        assert status3["papers"][0]["percentage"] == 85.0
        assert status3["papers"][0]["confidence_level"] == "high"

        # Test Decoupled Re-grade Reset
        await mgr.reset_batch_for_regrade(batch_id, "New stricter rubric")
        status4 = await mgr.get_status(batch_id)
        assert status4["rubric"] == "New stricter rubric"
        assert status4["current_phase"] == 2
        assert status4["status"] == "phase2_grading"
        assert status4["papers"][0]["ocr_text"] == "Transcribed student handwriting here"  # Preserved!
        assert status4["papers"][0]["marks"] is None  # Reset for regrade
        assert status4["papers"][0]["status"] == "ocr_done"
    asyncio.run(_test())

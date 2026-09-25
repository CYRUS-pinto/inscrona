import os
import time
import uuid
import json
import asyncio
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any

class StagedBatchManager:
    """
    Manages the two-phase staged batch grading pipeline.
    Phase 1: Sequential Bulk OCR (GLM-OCR held in memory for all papers)
    Phase 2: Sequential Bulk Grading (Llama 3.2:3B held in memory for all papers)
    Also supports instant re-grading over cached OCR transcripts without re-running vision OCR.
    """
    def __init__(self, db_path: str = "database.db"):
        self.db_path = db_path

    def _ensure_db(self, conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batches (
                batch_id TEXT PRIMARY KEY,
                rubric TEXT,
                engine TEXT,
                status TEXT,
                current_phase INTEGER DEFAULT 0,
                total_papers INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_papers (
                job_id TEXT PRIMARY KEY,
                batch_id TEXT,
                filename TEXT,
                file_path TEXT,
                ocr_text TEXT,
                marks REAL,
                max_marks REAL,
                percentage REAL,
                confidence REAL,
                confidence_level TEXT,
                feedback TEXT,
                status TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
            )
        """)

    async def init_db(self):
        def _init():
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_db(conn)
                conn.commit()
        await asyncio.to_thread(_init)

    async def create_batch(
        self,
        items: List[Dict[str, Any]],
        rubric: str,
        engine: str = "staged_local",
        batch_id: Optional[str] = None
    ) -> str:
        bid = batch_id or f"b_{uuid.uuid4().hex[:8]}"
        total = len(items)

        def _insert():
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_db(conn)
                conn.execute(
                    "INSERT INTO batches (batch_id, rubric, engine, status, current_phase, total_papers) VALUES (?, ?, ?, ?, ?, ?)",
                    (bid, rubric, engine, "queued", 0, total)
                )
                for it in items:
                    jid = it.get("job_id") or uuid.uuid4().hex[:12]
                    conn.execute(
                        """INSERT INTO batch_papers (job_id, batch_id, filename, file_path, status)
                           VALUES (?, ?, ?, ?, ?)""",
                        (jid, bid, it.get("filename", "upload.jpg"), it.get("file_path", ""), "pending")
                    )
                conn.commit()

        await asyncio.to_thread(_insert)
        return bid

    async def update_paper_ocr(self, job_id: str, ocr_text: str, error: Optional[str] = None):
        def _update():
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_db(conn)
                if error:
                    conn.execute(
                        "UPDATE batch_papers SET ocr_text = ?, status = 'failed', error_message = ? WHERE job_id = ?",
                        (ocr_text, error, job_id)
                    )
                else:
                    conn.execute(
                        "UPDATE batch_papers SET ocr_text = ?, status = 'ocr_done', error_message = NULL WHERE job_id = ?",
                        (ocr_text, job_id)
                    )
                conn.commit()
        await asyncio.to_thread(_update)

    async def update_paper_grade(
        self,
        job_id: str,
        marks: float,
        max_marks: float = 10.0,
        confidence: float = 0.8,
        feedback: str = "",
        error: Optional[str] = None
    ):
        percentage = (marks / max_marks * 100.0) if max_marks > 0 else 0.0
        conf_level = "high" if confidence >= 0.75 else ("medium" if confidence >= 0.5 else "low")

        def _update():
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_db(conn)
                if error:
                    conn.execute(
                        """UPDATE batch_papers 
                           SET marks = ?, max_marks = ?, percentage = ?, confidence = ?, confidence_level = ?, feedback = ?, status = 'failed', error_message = ?
                           WHERE job_id = ?""",
                        (marks, max_marks, percentage, confidence, conf_level, feedback, error, job_id)
                    )
                else:
                    conn.execute(
                        """UPDATE batch_papers 
                           SET marks = ?, max_marks = ?, percentage = ?, confidence = ?, confidence_level = ?, feedback = ?, status = 'graded', error_message = NULL
                           WHERE job_id = ?""",
                        (marks, max_marks, percentage, confidence, conf_level, feedback, job_id)
                    )
                conn.commit()
        await asyncio.to_thread(_update)

    async def set_batch_phase(self, batch_id: str, phase: int, status: str):
        def _update():
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_db(conn)
                conn.execute(
                    "UPDATE batches SET current_phase = ?, status = ? WHERE batch_id = ?",
                    (phase, status, batch_id)
                )
                conn.commit()
        await asyncio.to_thread(_update)

    async def reset_batch_for_regrade(self, batch_id: str, new_rubric: str):
        """
        Resets all papers to ocr_done and updates rubric, skipping vision OCR completely.
        """
        def _reset():
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_db(conn)
                conn.execute(
                    "UPDATE batches SET rubric = ?, current_phase = 2, status = 'phase2_grading' WHERE batch_id = ?",
                    (new_rubric, batch_id)
                )
                conn.execute(
                    "UPDATE batch_papers SET marks = NULL, max_marks = NULL, percentage = NULL, confidence = NULL, feedback = NULL, status = 'ocr_done', error_message = NULL WHERE batch_id = ?",
                    (batch_id,)
                )
                conn.commit()
        await asyncio.to_thread(_reset)

    async def get_status(self, batch_id: str) -> Dict[str, Any]:
        def _get():
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_db(conn)
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
                if not row:
                    raise ValueError(f"Batch {batch_id} not found")
                papers = conn.execute("SELECT * FROM batch_papers WHERE batch_id = ? ORDER BY created_at ASC", (batch_id,)).fetchall()
                
                paper_list = [dict(p) for p in papers]
                graded_count = sum(1 for p in paper_list if p["status"] == "graded")
                ocr_count = sum(1 for p in paper_list if p["ocr_text"] is not None)
                low_conf_count = sum(1 for p in paper_list if p.get("confidence") is not None and p["confidence"] < 0.70)

                return {
                    "batch_id": row["batch_id"],
                    "rubric": row["rubric"],
                    "engine": row["engine"],
                    "status": row["status"],
                    "current_phase": row["current_phase"],
                    "total_papers": row["total_papers"],
                    "ocr_completed": ocr_count,
                    "grading_completed": graded_count,
                    "review_needed_count": low_conf_count,
                    "created_at": row["created_at"],
                    "papers": paper_list
                }
        return await asyncio.to_thread(_get)

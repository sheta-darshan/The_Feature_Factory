"""
Tiny JSON-file-based job store. No database needed for single-PC use.
Each job is one file: jobs/<job_id>.json
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import JOBS_DIR


def new_job_id() -> str:
    return uuid.uuid4().hex[:10]


def job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def create_job(job_id: str, data: dict) -> dict:
    data = {
        "job_id": job_id,
        "status": "queued",           # queued -> processing -> done / failed
        "step": "waiting",            # human-readable current step
        "created_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "delivery_zip": None,
        **data,
    }
    save_job(job_id, data)
    return data


def save_job(job_id: str, data: dict):
    job_path(job_id).write_text(json.dumps(data, indent=2))


def load_job(job_id: str) -> Optional[dict]:
    p = job_path(job_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def update_job(job_id: str, **fields):
    data = load_job(job_id)
    if data is None:
        return None
    data.update(fields)
    save_job(job_id, data)
    return data


def list_jobs() -> list:
    jobs = [json.loads(p.read_text()) for p in JOBS_DIR.glob("*.json")]
    return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

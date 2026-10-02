"""
Thread-safe and Process-safe Project Metadata Manager
Provides file-locked reads, writes, and mutations for outputs/<project_id>/metadata.json
using filelock to eliminate race conditions between concurrent jobs and requests.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Callable, Optional
from filelock import FileLock


def get_project_dir(project_id: str) -> Path:
    """Return the output directory path for a project."""
    return Path("outputs") / project_id


def get_metadata_path(project_id: str) -> Path:
    """Return the metadata.json path for a project."""
    return get_project_dir(project_id) / "metadata.json"


def get_metadata_lock(project_id: str, timeout: float = 20.0) -> FileLock:
    """
    Return a FileLock instance for the project's metadata.json.
    Ensures directory exists before acquiring lock.
    """
    p_dir = get_project_dir(project_id)
    p_dir.mkdir(parents=True, exist_ok=True)
    lock_file = p_dir / "metadata.json.lock"
    return FileLock(str(lock_file), timeout=timeout)


def read_metadata(project_id: str) -> Dict[str, Any]:
    """Safely read metadata.json under lock."""
    with get_metadata_lock(project_id):
        m_path = get_metadata_path(project_id)
        if not m_path.exists():
            return {}
        try:
            return json.loads(m_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[MetadataManager] Warning: Failed reading {m_path}: {e}")
            return {}


def write_metadata(project_id: str, data: Dict[str, Any]):
    """Safely write metadata.json atomically under lock."""
    with get_metadata_lock(project_id):
        m_path = get_metadata_path(project_id)
        temp_path = m_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(m_path)


def update_metadata(project_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely load existing metadata, merge updates dict, and persist atomically under lock.
    Returns the updated metadata dict.
    """
    with get_metadata_lock(project_id):
        m_path = get_metadata_path(project_id)
        data = {}
        if m_path.exists():
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[MetadataManager] Warning: Overwriting unreadable {m_path}: {e}")
                data = {}
        data.update(updates)
        temp_path = m_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(m_path)
        return data


def mutate_metadata(project_id: str, mutate_fn: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    """
    Safely load existing metadata, pass it to mutate_fn for in-place modifications,
    and persist atomically under lock.
    """
    with get_metadata_lock(project_id):
        m_path = get_metadata_path(project_id)
        data = {}
        if m_path.exists():
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        mutate_fn(data)
        temp_path = m_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(m_path)
        return data

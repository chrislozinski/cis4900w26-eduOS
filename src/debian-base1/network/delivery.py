#!/usr/bin/env python3
"""
Teacher-side delivery store: target state hash, APPLY_ACK records, force_resend, collect flags.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

from .constants import DELIVERY_DIR


def _path(classroomId: str) -> str:
    return os.path.join(DELIVERY_DIR, f"{classroomId}.json")


def ensureDir() -> None:
    os.makedirs(DELIVERY_DIR, mode=0o775, exist_ok=True)


def _empty(classroomId: str) -> dict:
    return {
        "classroom_id": classroomId,
        "target_state_hash": None,
        "students": {},
        "collect_all": False,
    }


def load(classroomId: str) -> dict:
    ensureDir()
    path = _path(classroomId)
    if not os.path.isfile(path):
        return _empty(classroomId)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("classroom_id", classroomId)
        data.setdefault("students", {})
        data.setdefault("collect_all", False)
        return data
    except Exception:
        return _empty(classroomId)


def save(data: dict) -> None:
    ensureDir()
    classroomId = data["classroom_id"]
    path = _path(classroomId)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _studentEntry(data: dict, studentId: str) -> dict:
    students = data.setdefault("students", {})
    if studentId not in students:
        students[studentId] = {
            "acked_hash": None,
            "acked_at": None,
            "last_error": None,
            "force_resend": False,
            "collect_requested": False,
            "last_seen_ip": None,
        }
    return students[studentId]


def setTargetHash(classroomId: str, stateHash: str, roster: list[str]) -> None:
    data = load(classroomId)
    data["target_state_hash"] = stateHash
    for sid in roster:
        _studentEntry(data, sid)
    save(data)


def recordAck(
    classroomId: str,
    studentId: str,
    stateHash: str,
    ok: bool,
    error: Optional[str] = None,
    peerIp: Optional[str] = None,
) -> None:
    data = load(classroomId)
    entry = _studentEntry(data, studentId)
    if peerIp:
        entry["last_seen_ip"] = peerIp
    if ok:
        entry["acked_hash"] = stateHash
        entry["acked_at"] = datetime.now(timezone.utc).isoformat()
        entry["last_error"] = None
        entry["force_resend"] = False
    else:
        entry["last_error"] = error or "apply_failed"
        entry["acked_at"] = datetime.now(timezone.utc).isoformat()
    save(data)


def markForceResend(classroomId: str, studentId: str) -> None:
    data = load(classroomId)
    entry = _studentEntry(data, studentId)
    entry["force_resend"] = True
    save(data)


def markForceResendAllPending(classroomId: str) -> None:
    data = load(classroomId)
    target = data.get("target_state_hash")
    for sid, entry in data.get("students", {}).items():
        if entry.get("acked_hash") != target or entry.get("last_error"):
            entry["force_resend"] = True
    save(data)


def clearForceResend(classroomId: str, studentId: str) -> None:
    data = load(classroomId)
    entry = _studentEntry(data, studentId)
    entry["force_resend"] = False
    save(data)


def needsForceResend(classroomId: str, studentId: str) -> bool:
    data = load(classroomId)
    return bool(_studentEntry(data, studentId).get("force_resend"))


def requestCollect(classroomId: str, studentId: Optional[str] = None) -> None:
    """If studentId is None, collect from all rostered students on next hello."""
    data = load(classroomId)
    if studentId is None:
        data["collect_all"] = True
        for entry in data.get("students", {}).values():
            entry["collect_requested"] = True
    else:
        entry = _studentEntry(data, studentId)
        entry["collect_requested"] = True
    save(data)


def shouldCollect(classroomId: str, studentId: str) -> bool:
    data = load(classroomId)
    if data.get("collect_all"):
        return True
    return bool(_studentEntry(data, studentId).get("collect_requested"))


def clearCollect(classroomId: str, studentId: str) -> None:
    data = load(classroomId)
    entry = _studentEntry(data, studentId)
    entry["collect_requested"] = False
    # clear collect_all only when no one still requested
    if all(not e.get("collect_requested") for e in data.get("students", {}).values()):
        data["collect_all"] = False
    save(data)


def noteSeen(classroomId: str, studentId: str, peerIp: str) -> None:
    data = load(classroomId)
    entry = _studentEntry(data, studentId)
    entry["last_seen_ip"] = peerIp
    save(data)


def uiStatus(classroomId: str, studentId: str) -> tuple[str, str]:
    """
    Returns (label, subtitle) for enrolled list.
    Labels: delivered | pending | failed
    """
    data = load(classroomId)
    target = data.get("target_state_hash")
    entry = data.get("students", {}).get(studentId)
    if not entry:
        return "pending", "not yet synced"
    if entry.get("last_error") and entry.get("acked_hash") != target:
        at = entry.get("acked_at") or ""
        short = _fmtTime(at) if at else ""
        return "failed", short or (entry.get("last_error") or "error")
    if target and entry.get("acked_hash") == target and not entry.get("last_error"):
        return "delivered", _fmtTime(entry.get("acked_at") or "")
    if entry.get("acked_at") and entry.get("acked_hash"):
        return "pending", f"last ok: {_fmtTime(entry['acked_at'])}"
    return "pending", "not yet synced"


def _fmtTime(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except Exception:
        return iso[:16]


def workCacheHasBundles(classroomId: str) -> bool:
    from .constants import WORK_CACHE_DIR
    root = os.path.join(WORK_CACHE_DIR, classroomId)
    if not os.path.isdir(root):
        return False
    for name in os.listdir(root):
        sub = os.path.join(root, name)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "work.json")):
            return True
    return False


def queueWorkRestore(classroomId: str, studentId: str) -> None:
    """Mark teacher cache so next student hello gets APPLY_WORK."""
    from .constants import WORK_CACHE_DIR
    workDir = os.path.join(WORK_CACHE_DIR, classroomId, studentId)
    if not os.path.isdir(workDir):
        return
    open(os.path.join(workDir, ".restore_queued"), "w").close()

#!/usr/bin/env python3
"""Student state shape: build, validate, canonicalize, hash"""
import copy
import hashlib
import json
import os
from datetime import datetime, timezone

from .constants import STATE_SCHEMA_VERSION


def computeLessonsFingerprint(lessonIds, lessonsRoot):
    """Changes whenever an enabled lesson is republished, so sync re-delivers."""
    parts = []
    for lid in sorted(lessonIds or []):
        published = ""
        try:
            with open(os.path.join(lessonsRoot, lid, "meta.json"), "r", encoding="utf-8") as f:
                published = json.load(f).get("published_at", "")
        except Exception:
            try:
                published = str(os.path.getmtime(os.path.join(lessonsRoot, lid)))
            except OSError:
                pass
        parts.append(f"{lid}:{published}")
    if not parts:
        return ""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def buildStudentState(studentId: str, classroomObj: dict, lessonsFingerprint: str = "") -> dict:
    env = {
        "enabled_apps":    _normalizeApps(classroomObj.get("enabled_apps",    [])),
        "enabled_lessons": list(classroomObj.get("enabled_lessons", [])),
        "library_sites":   _normalizeSites(classroomObj.get("library_sites",  [])),
        "restricted_sites": list(classroomObj.get("restricted_sites", [])),
    }
    # Only include when present so lesson-less classrooms keep byte-identical hashes
    if lessonsFingerprint:
        env["lessons_fingerprint"] = lessonsFingerprint
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "student_id": studentId,
        "session": {
            "classroom_id":   classroomObj.get("id",   "_unassigned"),
            "classroom_name": classroomObj.get("name", "Your Class"),
        },
        "environment": env,
        "security": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signature": "",
        },
    }


def validateStudentState(state: dict) -> bool:
    for key in ("student_id", "session", "environment", "security", "schema_version"):
        if key not in state:
            raise ValueError(f"Missing required key: {key}")
    env = state["environment"]
    for field in ("enabled_apps", "enabled_lessons", "library_sites"):
        if not isinstance(env.get(field, []), list):
            raise ValueError(f"environment.{field} must be a list")
    return True


def canonicalizeStudentState(state: dict) -> bytes:
    """Stable byte representation for signing/hashing (signature field zeroed)."""
    normalized = copy.deepcopy(state)
    normalized.setdefault("security", {})["signature"] = ""
    return json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")


def computeStateHash(state: dict) -> str:
    """Full canonical hash including timestamp (signing/diagnostics)."""
    return hashlib.sha256(canonicalizeStudentState(state)).hexdigest()


def computeContentHash(state: dict) -> str:
    """
    Hash of student_id + session + environment only.
    Ignores signature and timestamp so noop detection stays stable across rebuilds.
    """
    normalized = copy.deepcopy(state)
    normalized.setdefault("security", {})
    normalized["security"]["signature"] = ""
    normalized["security"]["timestamp"] = ""
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def computeClassroomConfigHash(classroomObj: dict, lessonsFingerprint: str = "") -> str:
    """
    Classroom-level delivery target hash (shared by all roster students).
    Does not include student_id or timestamps.
    """
    payload = {
        "classroom_id": classroomObj.get("id", ""),
        "enabled_apps": _normalizeApps(classroomObj.get("enabled_apps", [])),
        "enabled_lessons": list(classroomObj.get("enabled_lessons", [])),
        "library_sites": _normalizeSites(classroomObj.get("library_sites", [])),
        "restricted_sites": list(classroomObj.get("restricted_sites", [])),
    }
    if lessonsFingerprint:
        payload["lessons_fingerprint"] = lessonsFingerprint
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# internal helper functions
def _normalizeApps(apps):
    return [a for a in apps if isinstance(a, dict) and a.get("label")]


def _normalizeSites(sites):
    out = []
    for s in sites:
        if isinstance(s, dict) and s.get("label") and s.get("url"):
            out.append({"label": s["label"], "url": s["url"], "icon": s.get("icon", "")})
    return out

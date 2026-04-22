#!/usr/bin/env python3
"""Student state shape: build, validate, canonicalize, hash"""
import copy
import hashlib
import json
from datetime import datetime, timezone

from .constants import STATE_SCHEMA_VERSION


def buildStudentState(studentId: str, classroomObj: dict) -> dict:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "student_id": studentId,
        "session": {
            "classroom_id":   classroomObj.get("id",   "_unassigned"),
            "classroom_name": classroomObj.get("name", "Your Class"),
        },
        "environment": {
            "enabled_apps":    _normalizeApps(classroomObj.get("enabled_apps",    [])),
            "enabled_lessons": list(classroomObj.get("enabled_lessons", [])),
            "library_sites":   _normalizeSites(classroomObj.get("library_sites",  [])),
            "restricted_sites": list(classroomObj.get("restricted_sites", [])),
        },
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
    return hashlib.sha256(canonicalizeStudentState(state)).hexdigest()


# internal helper functions
def _normalizeApps(apps):
    return [a for a in apps if isinstance(a, dict) and a.get("label")]


def _normalizeSites(sites):
    out = []
    for s in sites:
        if isinstance(s, dict) and s.get("label") and s.get("url"):
            out.append({"label": s["label"], "url": s["url"], "icon": s.get("icon", "")})
    return out

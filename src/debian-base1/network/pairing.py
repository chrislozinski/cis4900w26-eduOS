#!/usr/bin/env python3
"""
Join session state machine. Publisher owns code generation.
Classroom Manager reads status files and writes commands (IPC).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from .constants import (
    CONTROL_DIR,
    DEFAULT_SHARED_SECRET,
    JOIN_CODE_TTL_SECONDS,
    SECRETS_DIR,
)


def _statusPath(classroomId: str) -> str:
    return os.path.join(CONTROL_DIR, f"pairing-{classroomId}.json")


def _cmdPath(classroomId: str) -> str:
    return os.path.join(CONTROL_DIR, f"pairing-{classroomId}.cmd")


def _secretPath(classroomId: str) -> str:
    return os.path.join(SECRETS_DIR, classroomId)


def ensureDirs() -> None:
    os.makedirs(CONTROL_DIR, mode=0o775, exist_ok=True)
    os.makedirs(SECRETS_DIR, mode=0o770, exist_ok=True)


def getOrCreateClassroomSecret(classroomId: str) -> str:
    """Per-classroom HMAC secret. Not the ISO default for live joins."""
    ensureDirs()
    path = _secretPath(classroomId)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    secret = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(secret)
    try:
        os.chmod(path, 0o640)
    except OSError:
        pass
    return secret


def _hashCode(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _newCode() -> str:
    # 6 chars, easy to read aloud (no 0/O/1/I)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def readStatus(classroomId: str) -> dict:
    path = _statusPath(classroomId)
    if not os.path.isfile(path):
        return {
            "classroom_id": classroomId,
            "joining_enabled": False,
            "code_plain": None,
            "expires_at": None,
            "updated_at": None,
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "classroom_id": classroomId,
            "joining_enabled": False,
            "code_plain": None,
            "expires_at": None,
            "updated_at": None,
        }


def _writeStatus(data: dict) -> None:
    ensureDirs()
    path = _statusPath(data["classroom_id"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def openJoining(classroomId: str) -> dict:
    code = _newCode()
    expires = time.time() + JOIN_CODE_TTL_SECONDS
    data = {
        "classroom_id": classroomId,
        "joining_enabled": True,
        "code_plain": code,
        "code_hash": _hashCode(code),
        "expires_at": expires,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _writeStatus(data)
    getOrCreateClassroomSecret(classroomId)
    return data


def closeJoining(classroomId: str) -> dict:
    data = {
        "classroom_id": classroomId,
        "joining_enabled": False,
        "code_plain": None,
        "code_hash": None,
        "expires_at": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _writeStatus(data)
    return data


def refreshCodeIfNeeded(classroomId: str) -> dict:
    """If joining is open and code expired, mint a new one."""
    data = readStatus(classroomId)
    if not data.get("joining_enabled"):
        return data
    expires = data.get("expires_at") or 0
    if time.time() < float(expires):
        return data
    return openJoining(classroomId)


def verifyJoinCode(classroomId: str, code: str) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    Refreshes expired codes first so a stale UI code fails cleanly.
    """
    data = refreshCodeIfNeeded(classroomId)
    if not data.get("joining_enabled"):
        return False, "joining_closed"
    expires = float(data.get("expires_at") or 0)
    if time.time() > expires:
        return False, "code_expired"
    expected = (data.get("code_hash") or "")
    if _hashCode(code.strip().upper()) != expected:
        return False, "bad_code"
    return True, "ok"


def writeCommand(classroomId: str, command: str) -> None:
    """Classroom Manager writes open|close|refresh for the publisher to apply."""
    ensureDirs()
    path = _cmdPath(classroomId)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "command": command,
            "classroom_id": classroomId,
            "at": datetime.now(timezone.utc).isoformat(),
        }, f)


def consumeCommand(classroomId: str) -> Optional[str]:
    path = _cmdPath(classroomId)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        os.remove(path)
        return data.get("command")
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def applyPendingCommands(classroomIds: list[str]) -> None:
    for cid in classroomIds:
        cmd = consumeCommand(cid)
        if cmd == "open":
            st = readStatus(cid)
            if st.get("joining_enabled") and time.time() < float(st.get("expires_at") or 0):
                continue  # already open with a live code — do not remint
            openJoining(cid)
        elif cmd == "close":
            closeJoining(cid)
        elif cmd == "refresh":
            if readStatus(cid).get("joining_enabled"):
                openJoining(cid)


def isDevSecret(secret: str) -> bool:
    return secret == DEFAULT_SHARED_SECRET


def refuseLiveJoinWithDevSecret(secret: str, allowDev: bool) -> bool:
    """True if join should be refused."""
    if allowDev:
        return False
    return isDevSecret(secret)

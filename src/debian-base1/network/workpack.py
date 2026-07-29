#!/usr/bin/env python3
"""
Modular student work parts registry.
v1: makecode (WebKit profile pack/unpack).
Future apps register pack/unpack without changing REPORT/APPLY_WORK.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Callable, Optional

from .constants import WORK_CACHE_DIR


PartPackFn = Callable[[str, str], Optional[tuple[str, dict]]]
PartUnpackFn = Callable[[str, str, str], tuple[bool, str]]


def makecodeProfileDir(studentId: str, classroomId: str) -> str:
    home = os.path.expanduser(f"~{studentId}") if studentId else os.path.expanduser("~")
    # When running as the student user, ~ is enough
    if not os.path.isdir(home) or studentId == os.environ.get("USER"):
        home = os.path.expanduser("~")
    return os.path.join(
        home, ".local", "share", "makecode", classroomId, studentId or os.environ.get("USER", "student"),
        "makecodeProfile",
    )


def _packMakecode(studentId: str, classroomId: str) -> Optional[tuple[str, dict]]:
    src = makecodeProfileDir(studentId, classroomId)
    if not os.path.isdir(src):
        return None
    fd, tarPath = tempfile.mkstemp(suffix=".tar.gz")
    os.close(fd)
    with tarfile.open(tarPath, "w:gz") as tar:
        tar.add(src, arcname="makecodeProfile")
    meta = {
        "id": "makecode",
        "file": "makecode.tar.gz",
        "ok": True,
        "bytes": os.path.getsize(tarPath),
        "checksum": _sha256File(tarPath),
        "source": src,
    }
    return tarPath, meta


def _unpackMakecode(studentId: str, classroomId: str, tarPath: str) -> tuple[bool, str]:
    dest = makecodeProfileDir(studentId, classroomId)
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    if os.path.isdir(dest):
        bak = dest + ".bak-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        try:
            os.rename(dest, bak)
        except OSError as e:
            return False, f"cannot move live profile aside: {e}"
    try:
        with tarfile.open(tarPath, "r:gz") as tar:
            tar.extractall(parent)
        # ensure final name
        extracted = os.path.join(parent, "makecodeProfile")
        if extracted != dest and os.path.isdir(extracted):
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.rename(extracted, dest)
        return True, "ok"
    except Exception as e:
        return False, str(e)


PARTS: dict[str, dict] = {
    "makecode": {
        "pack": _packMakecode,
        "unpack": _unpackMakecode,
        "filename": "makecode.tar.gz",
    },
}


def _sha256File(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collectWorkBundle(studentId: str, classroomId: str, outDir: str) -> dict:
    """
    Pack all registered parts into outDir. Writes work.json.
    Returns the work.json dict.
    """
    os.makedirs(outDir, exist_ok=True)
    partsMeta = []
    for partId, spec in PARTS.items():
        result = spec["pack"](studentId, classroomId)
        if not result:
            continue
        tarPath, meta = result
        destName = spec["filename"]
        dest = os.path.join(outDir, destName)
        shutil.move(tarPath, dest)
        meta["file"] = destName
        partsMeta.append(meta)

    work = {
        "student_id": studentId,
        "classroom_id": classroomId,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "parts": partsMeta,
    }
    with open(os.path.join(outDir, "work.json"), "w", encoding="utf-8") as f:
        json.dump(work, f, indent=2)
    return work


def storeInTeacherCache(classroomId: str, studentId: str, bundleDir: str) -> str:
    dest = os.path.join(WORK_CACHE_DIR, classroomId, studentId)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(bundleDir, dest)
    return dest


def applyWorkBundle(studentId: str, classroomId: str, bundleDir: str) -> list[dict]:
    """Unpack each known part. Unknown part ids are skipped."""
    workPath = os.path.join(bundleDir, "work.json")
    with open(workPath, "r", encoding="utf-8") as f:
        work = json.load(f)
    results = []
    for part in work.get("parts", []):
        partId = part.get("id")
        if partId not in PARTS:
            results.append({"id": partId, "ok": False, "reason": "unknown_part"})
            continue
        fname = part.get("file") or PARTS[partId]["filename"]
        tarPath = os.path.join(bundleDir, fname)
        if not os.path.isfile(tarPath):
            results.append({"id": partId, "ok": False, "reason": "missing_file"})
            continue
        ok, reason = PARTS[partId]["unpack"](studentId, classroomId, tarPath)
        results.append({"id": partId, "ok": ok, "reason": reason})
    return results


def packLessonsArchive(lessonIds: list[str], lessonsRoot: str) -> Optional[str]:
    """Tar enabled lesson directories for apply payload. Returns temp tar path or None."""
    members = []
    for lid in lessonIds:
        path = os.path.join(lessonsRoot, lid)
        if os.path.isdir(path):
            members.append((path, lid))
    if not members:
        return None
    fd, tarPath = tempfile.mkstemp(suffix="-lessons.tar.gz")
    os.close(fd)
    with tarfile.open(tarPath, "w:gz") as tar:
        for path, arc in members:
            tar.add(path, arcname=arc)
    return tarPath


def unpackLessonsArchive(tarPath: str, destRoot: str) -> tuple[bool, str]:
    os.makedirs(destRoot, exist_ok=True)
    try:
        with tarfile.open(tarPath, "r:gz") as tar:
            tar.extractall(destRoot)
        return True, "ok"
    except Exception as e:
        return False, str(e)

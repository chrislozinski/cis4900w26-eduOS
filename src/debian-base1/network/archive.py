#!/usr/bin/env python3
"""
Timestamped classroom export / import.
Export freezes classroom.json + collected student-data from teacher work cache.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from typing import Optional

from .constants import DEFAULT_CLASSROOMS_FILE, WORK_CACHE_DIR


def _sanitizeName(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", name.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "classroom"


def exportClassroom(
    classroomId: str,
    parentDir: str,
    classroomsFile: str = DEFAULT_CLASSROOMS_FILE,
) -> str:
    """
    Create <Name>-<YYYYMMDD-HHMMSS>/ under parentDir.
    Returns path to the new folder.
    """
    with open(classroomsFile, "r", encoding="utf-8") as f:
        data = json.load(f)

    cls = None
    for c in data.get("classrooms", []):
        if c.get("id") == classroomId:
            cls = c
            break
    if not cls:
        raise ValueError(f"classroom not found: {classroomId}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folderName = f"{_sanitizeName(cls.get('name', classroomId))}-{stamp}"
    outRoot = os.path.join(parentDir, folderName)
    os.makedirs(outRoot, exist_ok=True)

    # classroom.json: this classroom + web_apps needed for import
    payload = {
        "classroom": cls,
        "web_apps": data.get("web_apps", []),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(os.path.join(outRoot, "classroom.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    studentData = os.path.join(outRoot, "student-data")
    os.makedirs(studentData, exist_ok=True)
    cacheRoot = os.path.join(WORK_CACHE_DIR, classroomId)
    if os.path.isdir(cacheRoot):
        for sid in os.listdir(cacheRoot):
            src = os.path.join(cacheRoot, sid)
            if not os.path.isdir(src):
                continue
            if not os.path.isfile(os.path.join(src, "work.json")):
                continue
            dest = os.path.join(studentData, sid)
            if os.path.isdir(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)

    return outRoot


def importClassroom(
    sourcePath: str,
    classroomsFile: str = DEFAULT_CLASSROOMS_FILE,
    replaceExisting: bool = False,
) -> str:
    """
    Import from a folder or a classroom.json path.
    Returns classroom id imported.
    """
    if os.path.isfile(sourcePath):
        folder = os.path.dirname(sourcePath)
        manifestPath = sourcePath
    else:
        folder = sourcePath
        manifestPath = os.path.join(folder, "classroom.json")

    with open(manifestPath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    cls = payload.get("classroom") or payload
    classroomId = cls.get("id")
    if not classroomId:
        raise ValueError("classroom.json missing id")

    if os.path.isfile(classroomsFile):
        with open(classroomsFile, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"classrooms": [], "web_apps": []}
    data.setdefault("classrooms", [])
    data.setdefault("web_apps", [])

    existingIdx = None
    for i, c in enumerate(data["classrooms"]):
        if c.get("id") == classroomId:
            existingIdx = i
            break
    if existingIdx is not None and not replaceExisting:
        raise FileExistsError(f"classroom id already exists: {classroomId}")
    if existingIdx is not None:
        data["classrooms"][existingIdx] = cls
    else:
        data["classrooms"].append(cls)

    # merge web apps by label
    have = {w.get("label") for w in data["web_apps"]}
    for wa in payload.get("web_apps", []):
        if wa.get("label") and wa["label"] not in have:
            data["web_apps"].append(wa)
            have.add(wa["label"])

    os.makedirs(os.path.dirname(classroomsFile) or ".", exist_ok=True)
    tmp = classroomsFile + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, classroomsFile)

    # restore work cache
    studentData = os.path.join(folder, "student-data")
    if os.path.isdir(studentData):
        destRoot = os.path.join(WORK_CACHE_DIR, classroomId)
        os.makedirs(destRoot, exist_ok=True)
        for sid in os.listdir(studentData):
            src = os.path.join(studentData, sid)
            if not os.path.isdir(src):
                continue
            dest = os.path.join(destRoot, sid)
            if os.path.isdir(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)

    return classroomId


def findClassroomJson(path: str) -> Optional[str]:
    if os.path.isfile(path) and path.endswith(".json"):
        return path
    candidate = os.path.join(path, "classroom.json")
    if os.path.isfile(candidate):
        return candidate
    return None

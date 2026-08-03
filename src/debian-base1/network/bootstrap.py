#!/usr/bin/env python3
"""
Ensure /shared live classrooms DB and network dirs exist before publisher/agent work.

Seed source (in order): /opt/cis4900/classrooms.json, then skel copy.
Live DB always stays at /shared/classrooms.json (never publisher-only on /opt).
"""
from __future__ import annotations

import json
import os
import shutil

from .constants import (
    CONTROL_DIR,
    DEFAULT_CLASSROOMS_FILE,
    DELIVERY_DIR,
    SECRETS_DIR,
    TEACHER_LESSONS_DIR,
    WORK_CACHE_DIR,
)

_SEED_CANDIDATES = (
    "/opt/cis4900/classrooms.json",
    "/etc/skel/.config/launcher/classrooms.json",
)

_MINIMAL = {
    "classrooms": [
        {
            "id": "class001",
            "name": "Class 001",
            "students": ["studentuser"],
            "enabled_apps": [],
            "enabled_lessons": [],
        }
    ],
    "web_apps": [],
}


def _needsSeed(path: str) -> bool:
    if not os.path.isfile(path):
        return True
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        classrooms = data.get("classrooms")
        return not isinstance(classrooms, list) or len(classrooms) == 0
    except Exception:
        return True


def _atomicWriteJson(path: str, data: dict) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _tryChownTeacher(path: str) -> None:
    try:
        import grp
        import pwd

        uid = pwd.getpwnam("root").pw_uid
        gid = grp.getgrnam("teacher").gr_gid
        os.chown(path, uid, gid)
    except Exception:
        pass


def ensureSharedDirs() -> None:
    for d, mode in (
        (os.path.dirname(DEFAULT_CLASSROOMS_FILE) or "/shared", 0o775),
        (TEACHER_LESSONS_DIR, 0o1777),
        (CONTROL_DIR, 0o775),
        (WORK_CACHE_DIR, 0o775),
        (DELIVERY_DIR, 0o775),
        (SECRETS_DIR, 0o770),
    ):
        os.makedirs(d, exist_ok=True)
        try:
            os.chmod(d, mode)
        except OSError:
            pass
        _tryChownTeacher(d)


def ensureSharedClassrooms(classroomsFile: str | None = None) -> str:
    """
    Bootstrap /shared/classrooms.json when missing or classrooms list empty.
    Returns the path used.
    """
    path = classroomsFile or os.environ.get(
        "CIS4900_CLASSROOMS_FILE", DEFAULT_CLASSROOMS_FILE
    )
    ensureSharedDirs()

    if not _needsSeed(path):
        try:
            os.chmod(path, 0o664)
        except OSError:
            pass
        _tryChownTeacher(path)
        return path

    seeded = False
    for src in _SEED_CANDIDATES:
        if os.path.isfile(src):
            try:
                tmp = path + ".tmp"
                shutil.copy2(src, tmp)
                os.replace(tmp, path)
                seeded = True
                print(f"[bootstrap] seeded {path} from {src}")
                break
            except Exception as e:
                print(f"[bootstrap] copy from {src} failed: {e}")

    if not seeded:
        _atomicWriteJson(path, _MINIMAL)
        print(f"[bootstrap] seeded {path} with minimal default")

    try:
        os.chmod(path, 0o664)
    except OSError:
        pass
    _tryChownTeacher(path)
    return path

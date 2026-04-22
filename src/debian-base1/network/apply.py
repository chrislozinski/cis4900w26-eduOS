#!/usr/bin/env python3
"""Atomic JSON state writes. Each target is independent so that one failing does not block the other"""
import json
import os
import tempfile

from .constants import DEFAULT_STATE_PATH

RUNTIME_STATE_PATH = os.path.expanduser("~/.cache/cis4900/student-state.json")


def applyStudentState(state: dict, systemPath: str = DEFAULT_STATE_PATH) -> dict:
    """
    Write state to the runtime cache (~/.cache/cis4900/) and the system path (/var/lib/cis4900/).

    The runtime cache is what the desktop apps read and always succeeds for a normal user.
    The system path requires /var/lib/cis4900 to be pre-created with correct ownership
    in the build hook (see 05-services.sh).
    """
    results = {}

    for label, path in (("runtime", RUNTIME_STATE_PATH), ("system", systemPath)):
        try:
            _atomicWrite(path, state)
            results[label] = path
        except PermissionError:
            if label == "system":
                print(
                    f"[apply] WARNING: no write permission for {path}. "
                    f"Fix in build hook: mkdir -p {os.path.dirname(path)} && "
                    f"chown studentuser:studentuser {os.path.dirname(path)}"
                )
        except Exception as e:
            print(f"[apply] WARNING: {label} write failed ({path}): {e}")

    if not results:
        raise RuntimeError("All state write targets failed")
    return results


def _atomicWrite(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-state-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

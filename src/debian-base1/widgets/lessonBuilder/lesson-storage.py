#!/usr/bin/env python3
"""
lesson-storage.py
Write-only: all disk operations for lesson drafts, publishing, trash, and recovery.
Never reads the catalog — use lesson-list.py for that.
"""
import json
import os
import shutil
import uuid
from datetime import datetime, timezone

TEACHER_LESSONS_SHARED_DIR = "/shared/teacher-lessons"
LOCAL_BASE_DIR   = os.path.expanduser("~/.local/share/cis4900/lesson-builder")
LOCAL_DRAFT_DIR  = os.path.join(LOCAL_BASE_DIR, "drafts")
LOCAL_TRASH_DIR  = os.path.join(LOCAL_BASE_DIR, "trash")
LOCAL_INDEX_FILE = os.path.join(LOCAL_BASE_DIR, "index.json")
CLASSROOMS_FILE  = "/shared/classrooms.json"


# Helpers

def _ensure_dirs():
    for d in (LOCAL_DRAFT_DIR, LOCAL_TRASH_DIR, TEACHER_LESSONS_SHARED_DIR):
        try:
            os.makedirs(d, mode=0o775, exist_ok=True)
        except OSError:
            pass


def _atomic_write(path, data_str):
    """Write a string to path atomically via a .tmp sibling."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data_str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _load_classrooms():
    if os.path.isfile(CLASSROOMS_FILE):
        try:
            with open(CLASSROOMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"classrooms": [], "web_apps": []}


def _save_classrooms(data):
    _atomic_write(CLASSROOMS_FILE, json.dumps(data, indent=2))


def _get_username():
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        return "teacher"


# Index

def load_drafts_index():
    """Return the list of draft entries from index.json (fast listing)."""
    if os.path.isfile(LOCAL_INDEX_FILE):
        try:
            with open(LOCAL_INDEX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            pass
    return []


def _save_drafts_index(entries):
    _ensure_dirs()
    _atomic_write(LOCAL_INDEX_FILE, json.dumps(entries, indent=2))


def _update_index_entry(lesson_id, fields):
    """Upsert fields into the index entry for lesson_id."""
    entries = load_drafts_index()
    for entry in entries:
        if entry.get("id") == lesson_id:
            entry.update(fields)
            _save_drafts_index(entries)
            return
    entries.append({"id": lesson_id, **fields})
    _save_drafts_index(entries)


def _remove_index_entry(lesson_id):
    entries = [e for e in load_drafts_index() if e.get("id") != lesson_id]
    _save_drafts_index(entries)


# Draft CRUD

def create_draft(title, lesson_type="makecode", description="", classroom_id=""):
    """
    Generate a new UUID, create the draft directory and blank files.
    Returns the lesson_id string ("teacher_<uuid>").
    """
    _ensure_dirs()
    lesson_id = f"teacher_{uuid.uuid4()}"
    draft_dir = os.path.join(LOCAL_DRAFT_DIR, lesson_id)
    os.makedirs(draft_dir, mode=0o775, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    meta = {
        "id":           lesson_id,
        "title":        title,
        "description":  description,
        "lesson_type":  lesson_type,
        "applications": [lesson_type],
        "created_at":   now,
        "author":       _get_username(),
        "published_to": [],
        "classroom_id": classroom_id,
    }
    draft = {
        "id":            lesson_id,
        "title":         title,
        "description":   description,
        "lesson_type":   lesson_type,
        "applications":  [lesson_type],
        "steps":         [],
        "solution_code": "",
        "classroom_id":  classroom_id,
    }

    _atomic_write(os.path.join(draft_dir, "meta.json"), json.dumps(meta, indent=2))
    _atomic_write(os.path.join(draft_dir, "draft.json"), json.dumps(draft, indent=2))
    _update_index_entry(lesson_id, {
        "title":        title,
        "lesson_type":  lesson_type,
        "published_to": [],
        "created_at":   now,
        "classroom_id": classroom_id,
    })
    return lesson_id


def load_draft(lesson_id):
    """Read and return draft.json for lesson_id, or None if missing."""
    path = os.path.join(LOCAL_DRAFT_DIR, lesson_id, "draft.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_draft(lesson_id, draft_data):
    """Atomically write draft_data to drafts/<lesson_id>/draft.json."""
    _ensure_dirs()
    draft_dir = os.path.join(LOCAL_DRAFT_DIR, lesson_id)
    os.makedirs(draft_dir, mode=0o775, exist_ok=True)
    _atomic_write(
        os.path.join(draft_dir, "draft.json"),
        json.dumps(draft_data, indent=2),
    )
    _update_index_entry(lesson_id, {
        "title":       draft_data.get("title", ""),
        "lesson_type": draft_data.get("lesson_type", "makecode"),
    })


def load_draft_meta(lesson_id):
    """Read and return meta.json for lesson_id, or None if missing."""
    path = os.path.join(LOCAL_DRAFT_DIR, lesson_id, "meta.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_draft_meta(lesson_id, meta):
    draft_dir = os.path.join(LOCAL_DRAFT_DIR, lesson_id)
    os.makedirs(draft_dir, mode=0o775, exist_ok=True)
    _atomic_write(os.path.join(draft_dir, "meta.json"), json.dumps(meta, indent=2))


# Publish / Unpublish

def publish_lesson(lesson_id, tutorial_md, solution_code, classroom_id):
    """
    Write tutorial.md, solution.ts, and meta.json to /shared/teacher-lessons/<lesson_id>/.
    Then add lesson_id to the target classroom's enabled_lessons in classrooms.json.
    """
    _ensure_dirs()
    shared_dir = os.path.join(TEACHER_LESSONS_SHARED_DIR, lesson_id)
    os.makedirs(shared_dir, mode=0o775, exist_ok=True)

    _atomic_write(os.path.join(shared_dir, "tutorial.md"), tutorial_md)
    _atomic_write(os.path.join(shared_dir, "solution.ts"), solution_code or "")

    local_meta   = load_draft_meta(lesson_id) or {}
    published_to = local_meta.get("published_to", [])
    if classroom_id and classroom_id not in published_to:
        published_to.append(classroom_id)

    shared_meta = {
        "id":           lesson_id,
        "title":        local_meta.get("title", ""),
        "description":  local_meta.get("description", ""),
        "author":       local_meta.get("author", _get_username()),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "published_to": published_to,
        "draft":        False,
    }
    _atomic_write(os.path.join(shared_dir, "meta.json"), json.dumps(shared_meta, indent=2))

    local_meta["published_to"] = published_to
    _save_draft_meta(lesson_id, local_meta)
    _update_index_entry(lesson_id, {"published_to": published_to})

    if classroom_id:
        classrooms = _load_classrooms()
        for cls in classrooms.get("classrooms", []):
            if cls["id"] == classroom_id:
                enabled = cls.setdefault("enabled_lessons", [])
                if lesson_id not in enabled:
                    enabled.append(lesson_id)
        _save_classrooms(classrooms)


def unpublish_lesson(lesson_id, classroom_id):
    """Remove lesson_id from the given classroom's enabled_lessons."""
    classrooms = _load_classrooms()
    changed = False
    for cls in classrooms.get("classrooms", []):
        if cls["id"] == classroom_id:
            before = cls.get("enabled_lessons", [])
            after  = [i for i in before if i != lesson_id]
            if after != before:
                cls["enabled_lessons"] = after
                changed = True
    if changed:
        _save_classrooms(classrooms)

    local_meta = load_draft_meta(lesson_id)
    if local_meta:
        published_to = [c for c in local_meta.get("published_to", []) if c != classroom_id]
        local_meta["published_to"] = published_to
        _save_draft_meta(lesson_id, local_meta)
        _update_index_entry(lesson_id, {"published_to": published_to})


def _unpublish_from_all(lesson_id):
    """Remove lesson_id from every classroom's enabled_lessons."""
    classrooms = _load_classrooms()
    changed = False
    for cls in classrooms.get("classrooms", []):
        before = cls.get("enabled_lessons", [])
        after  = [i for i in before if i != lesson_id]
        if after != before:
            cls["enabled_lessons"] = after
            changed = True
    if changed:
        _save_classrooms(classrooms)


# Trash / Delete

def move_to_bin(lesson_id):
    """Soft-delete: move draft directory to trash and unpublish from all classrooms."""
    _ensure_dirs()
    src = os.path.join(LOCAL_DRAFT_DIR, lesson_id)
    dst = os.path.join(LOCAL_TRASH_DIR, lesson_id)
    if os.path.isdir(src):
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.move(src, dst)
    _unpublish_from_all(lesson_id)
    _remove_index_entry(lesson_id)


def recover_draft(lesson_id):
    """Move a trashed lesson back to drafts."""
    _ensure_dirs()
    src = os.path.join(LOCAL_TRASH_DIR, lesson_id)
    dst = os.path.join(LOCAL_DRAFT_DIR, lesson_id)
    if not os.path.isdir(src):
        return
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.move(src, dst)
    meta = load_draft_meta(lesson_id) or {}
    _update_index_entry(lesson_id, {
        "title":        meta.get("title", ""),
        "lesson_type":  meta.get("lesson_type", "makecode"),
        "published_to": meta.get("published_to", []),
        "classroom_id": meta.get("classroom_id", ""),
    })


def permanent_delete(lesson_id):
    """Permanently remove the trash entry and shared published files (if any)."""
    trash_dir  = os.path.join(LOCAL_TRASH_DIR, lesson_id)
    shared_dir = os.path.join(TEACHER_LESSONS_SHARED_DIR, lesson_id)
    if os.path.isdir(trash_dir):
        shutil.rmtree(trash_dir)
    if os.path.isdir(shared_dir):
        shutil.rmtree(shared_dir)


def load_trash_index():
    """Return a list of meta dicts for all lessons currently in trash."""
    results = []
    if not os.path.isdir(LOCAL_TRASH_DIR):
        return results
    try:
        entries = os.listdir(LOCAL_TRASH_DIR)
    except OSError:
        return results
    for entry in sorted(entries):
        meta_path = os.path.join(LOCAL_TRASH_DIR, entry, "meta.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
            except Exception:
                pass
    return results


# Preview

def write_preview(lesson_id, tutorial_md):
    """
    Write tutorial.md to /shared/teacher-lessons/<lesson_id>/ marked as draft:True.
    Used for preview only — build_lesson_catalog() skips draft:True entries.
    """
    _ensure_dirs()
    shared_dir = os.path.join(TEACHER_LESSONS_SHARED_DIR, lesson_id)
    os.makedirs(shared_dir, mode=0o775, exist_ok=True)
    _atomic_write(os.path.join(shared_dir, "tutorial.md"), tutorial_md)
    stub_meta = {"id": lesson_id, "title": "Preview", "draft": True}
    _atomic_write(os.path.join(shared_dir, "meta.json"), json.dumps(stub_meta))


def cleanup_preview(lesson_id):
    """Remove the shared preview directory if it is still marked draft:True."""
    shared_dir = os.path.join(TEACHER_LESSONS_SHARED_DIR, lesson_id)
    meta_path  = os.path.join(shared_dir, "meta.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("draft", False):
                shutil.rmtree(shared_dir, ignore_errors=True)
        except Exception:
            pass

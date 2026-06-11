#!/usr/bin/env python3
"""
lesson-storage.py
Disk operations for lessons, publishing, recycling bin, and recovery.
All lesson data lives in two flat JSON files: lessons.json and recycling.json.
"""
import json
import os
import shutil
import uuid
from datetime import datetime, timezone

TEACHER_LESSONS_SHARED_DIR = "/shared/teacher-lessons"
LOCAL_BASE_DIR       = os.path.expanduser("~/.local/share/cis4900/lesson-builder")
LOCAL_LESSONS_FILE   = os.path.join(LOCAL_BASE_DIR, "lessons.json")
LOCAL_RECYCLING_FILE = os.path.join(LOCAL_BASE_DIR, "recycling.json")
CLASSROOMS_FILE      = "/shared/classrooms.json"


# Helpers

def _ensure_dirs():
    for d in (LOCAL_BASE_DIR, TEACHER_LESSONS_SHARED_DIR):
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


def _load_json_list(path):
    """Read a JSON file that contains a list. Returns [] on any error."""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            pass
    return []


# Lesson CRUD

def load_all_lessons():
    """Return the list of all lesson objects from lessons.json."""
    return _load_json_list(LOCAL_LESSONS_FILE)


def load_lesson(lesson_id):
    """Find and return a single lesson by id, or None if not found."""
    for l in _load_json_list(LOCAL_LESSONS_FILE):
        if l.get("id") == lesson_id:
            return l
    return None


def save_lesson(lesson_id, lesson_data):
    """Replace the lesson with lesson_id in lessons.json (upserts if missing)."""
    _ensure_dirs()
    lessons = _load_json_list(LOCAL_LESSONS_FILE)
    for i, l in enumerate(lessons):
        if l.get("id") == lesson_id:
            lessons[i] = lesson_data
            _atomic_write(LOCAL_LESSONS_FILE, json.dumps(lessons, indent=2))
            return
    lessons.append(lesson_data)
    _atomic_write(LOCAL_LESSONS_FILE, json.dumps(lessons, indent=2))


def create_lesson(title, lesson_type="makecode", description="", classroom_id=""):
    """
    Append a new blank lesson to lessons.json.
    Returns the lesson_id string ("teacher_<uuid>").
    """
    _ensure_dirs()
    lesson_id = f"teacher_{uuid.uuid4()}"
    now = datetime.now(timezone.utc).isoformat()
    lesson = {
        "id":            lesson_id,
        "title":         title,
        "description":   description,
        "lesson_type":   lesson_type,
        "status":        "draft",
        "published_to":  [],
        "classroom_id":  classroom_id,
        "created_at":    now,
        "author":        _get_username(),
        "steps":         [],
        "solution_code": "",
    }
    lessons = _load_json_list(LOCAL_LESSONS_FILE)
    lessons.append(lesson)
    _atomic_write(LOCAL_LESSONS_FILE, json.dumps(lessons, indent=2))
    return lesson_id


# Recycling bin

def load_recycling():
    """Return the list of recycled lesson objects from recycling.json."""
    return _load_json_list(LOCAL_RECYCLING_FILE)


def move_to_bin(lesson_id):
    """Soft-delete: move lesson from lessons.json to recycling.json and unpublish from all classrooms."""
    _ensure_dirs()
    lessons = _load_json_list(LOCAL_LESSONS_FILE)
    lesson  = next((l for l in lessons if l.get("id") == lesson_id), None)
    if not lesson:
        return
    _atomic_write(LOCAL_LESSONS_FILE,
                  json.dumps([l for l in lessons if l.get("id") != lesson_id], indent=2))
    recycling = _load_json_list(LOCAL_RECYCLING_FILE)
    recycling.append(lesson)
    _atomic_write(LOCAL_RECYCLING_FILE, json.dumps(recycling, indent=2))
    _unpublish_from_all(lesson_id)


def recover_lesson(lesson_id):
    """Move a recycled lesson back to lessons.json."""
    _ensure_dirs()
    recycling = _load_json_list(LOCAL_RECYCLING_FILE)
    lesson    = next((l for l in recycling if l.get("id") == lesson_id), None)
    if not lesson:
        return
    _atomic_write(LOCAL_RECYCLING_FILE,
                  json.dumps([l for l in recycling if l.get("id") != lesson_id], indent=2))
    lessons = _load_json_list(LOCAL_LESSONS_FILE)
    lessons.append(lesson)
    _atomic_write(LOCAL_LESSONS_FILE, json.dumps(lessons, indent=2))


def permanent_delete(lesson_id):
    """Permanently remove from recycling.json and delete published shared files."""
    recycling = _load_json_list(LOCAL_RECYCLING_FILE)
    _atomic_write(LOCAL_RECYCLING_FILE,
                  json.dumps([l for l in recycling if l.get("id") != lesson_id], indent=2))
    shared_dir = os.path.join(TEACHER_LESSONS_SHARED_DIR, lesson_id)
    if os.path.isdir(shared_dir):
        shutil.rmtree(shared_dir)


# Publish / Unpublish

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


def publish_lesson(lesson_id, tutorial_md, solution_code, classroom_id):
    """
    Write tutorial.md, solution.ts, and meta.json to /shared/teacher-lessons/<lesson_id>/.
    Updates lessons.json entry: status="published", published_to list updated.
    Adds lesson_id to the target classroom's enabled_lessons in classrooms.json.
    """
    _ensure_dirs()
    shared_dir = os.path.join(TEACHER_LESSONS_SHARED_DIR, lesson_id)
    os.makedirs(shared_dir, mode=0o775, exist_ok=True)

    _atomic_write(os.path.join(shared_dir, "tutorial.md"), tutorial_md)
    _atomic_write(os.path.join(shared_dir, "solution.ts"), solution_code or "")

    lesson = load_lesson(lesson_id) or {}
    published_to = lesson.get("published_to", [])
    if classroom_id and classroom_id not in published_to:
        published_to.append(classroom_id)
    lesson["published_to"] = published_to
    lesson["status"] = "published"
    save_lesson(lesson_id, lesson)

    shared_meta = {
        "id":           lesson_id,
        "title":        lesson.get("title", ""),
        "description":  lesson.get("description", ""),
        "author":       lesson.get("author", _get_username()),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "published_to": published_to,
        "draft":        False,
    }
    _atomic_write(os.path.join(shared_dir, "meta.json"), json.dumps(shared_meta, indent=2))

    if classroom_id:
        classrooms = _load_classrooms()
        for cls in classrooms.get("classrooms", []):
            if cls["id"] == classroom_id:
                enabled = cls.setdefault("enabled_lessons", [])
                if lesson_id not in enabled:
                    enabled.append(lesson_id)
        _save_classrooms(classrooms)


def unpublish_lesson(lesson_id, classroom_id):
    """Remove lesson_id from the given classroom's enabled_lessons. Updates lessons.json status."""
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

    lesson = load_lesson(lesson_id)
    if lesson:
        published_to = [c for c in lesson.get("published_to", []) if c != classroom_id]
        lesson["published_to"] = published_to
        if not published_to:
            lesson["status"] = "draft"
        save_lesson(lesson_id, lesson)


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

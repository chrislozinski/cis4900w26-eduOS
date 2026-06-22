#!/usr/bin/env python3
"""
lesson-list.py
Read-only: load published teacher lessons and build the full lesson catalog.
Never writes to disk. Import this wherever the catalog is needed.
"""
import json
import os

TEACHER_LESSONS_SHARED_DIR = "/shared/teacher-lessons"

BUILTIN_LESSON_CATALOG = [
    {
        "id":          "course_csintro1",
        "type":        "Course",
        "title":       "CS Intro 1",
        "description": "Core intro course with guided lessons and projects.",
        "url":         "/docs/courses/csintro1.html",
        "thumb":       "/docs/static/hero.svg",
    },
    {
        "id":          "course_csintro2",
        "type":        "Course",
        "title":       "CS Intro 2",
        "description": "Functions, tilemaps, logic, arrays, and projects.",
        "url":         "/docs/courses/csintro2.html",
        "thumb":       "/docs/static/hero.svg",
    },
    {
        "id":          "course_csintro3",
        "type":        "Course",
        "title":       "CS Intro 3",
        "description": "TypeScript-focused intermediate CS content.",
        "url":         "/docs/courses/csintro3.html",
        "thumb":       "/docs/static/hero.svg",
    },
    {
        "id":          "skillmap_beginner",
        "type":        "Skillmap",
        "title":       "Beginner Skillmap",
        "description": "Step-by-step interactive coding path.",
        "url":         "/--skillmap#beginner",
        "thumb":       "/docs/static/hero.svg",
    },
    {
        "id":          "open_editor",
        "type":        "Editor",
        "title":       "Open Free Editor",
        "description": "Start a new project from scratch.",
        "url":         "/",
        "thumb":       "/docs/static/icons/js.svg",
    },
]


def load_published_lessons():
    """
    Scan TEACHER_LESSONS_SHARED_DIR for subdirectories with a meta.json.
    Returns a list of meta dicts for lessons where draft != True.
    """
    results = []
    if not os.path.isdir(TEACHER_LESSONS_SHARED_DIR):
        return results
    try:
        entries = os.listdir(TEACHER_LESSONS_SHARED_DIR)
    except OSError:
        return results
    for entry in sorted(entries):
        lesson_dir = os.path.join(TEACHER_LESSONS_SHARED_DIR, entry)
        if not os.path.isdir(lesson_dir):
            continue
        meta_path = os.path.join(lesson_dir, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        if meta.get("draft", False):
            continue
        if not meta.get("id"):
            continue
        results.append(meta)
    return results


def lesson_to_catalog_entry(meta):
    """
    Convert a teacher lesson meta dict to a LESSON_CATALOG-compatible entry.
    Teacher lessons are served via the /api/md/teacher-lessons/ HTTP route.
    """
    lesson_id = meta["id"]
    return {
        "id":          lesson_id,
        "type":        "Tutorial",
        "title":       meta.get("title", "Untitled Lesson"),
        "description": meta.get("description", ""),
        "url":         f"/#tutorial:/api/md/teacher-lessons/{lesson_id}/tutorial",
        "thumb":       "/docs/static/hero.svg",
        "badge_color": "#3d9970",
    }


def build_lesson_catalog():
    """
    Return the full lesson catalog: builtin entries + published teacher lessons.
    Call this fresh each time a catalog is needed (it scans the filesystem).
    """
    catalog = list(BUILTIN_LESSON_CATALOG)
    for meta in load_published_lessons():
        try:
            catalog.append(lesson_to_catalog_entry(meta))
        except Exception:
            continue
    return catalog

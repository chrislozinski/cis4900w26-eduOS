#!/usr/bin/env python3
"""
convert-lesson.py
Single responsibility: convert a LessonDraft dict into valid MakeCode tutorial markdown.
"""


def convert_lesson(draft):
    """
    Convert a draft dict (as stored in draft.json) into a MakeCode tutorial .md string.

    The generated format follows tutorial-template.md:
      - Title header + @explicitHints annotation
      - Introduction @showdialog step using the lesson description
      - One ## {Step Title} section per step, with optional hint and tutorialhint code block
      - A final "Well Done!" closing step
    """
    title       = draft.get("title", "Untitled Lesson")
    description = draft.get("description", "Welcome to this tutorial.")
    steps       = draft.get("steps", [])

    lines = [
        f"# {title}",
        "### @explicitHints true",
        "",
        "## Introduction @showdialog",
        description or "Welcome to this tutorial.",
        "",
    ]

    for step in steps:
        step_title    = step.get("name") or step.get("title", "Step")
        instructions  = (step.get("description") or step.get("instructions") or "").strip()
        hint          = (step.get("hint") or "").strip()
        captured_code = (step.get("raw_ts") or step.get("captured_code") or "").strip()

        lines.append(f"## {{{step_title}}}")
        lines.append("")
        if instructions:
            lines.append(instructions)
            lines.append("")
        if hint:
            lines.append(f"~hint {hint}")
            lines.append("")
            lines.append("hint~")
            lines.append("")
        if captured_code:
            lines.append("#### ~ tutorialhint")
            lines.append("```blocks")
            lines.append(captured_code)
            lines.append("```")
            lines.append("")

    lines.append("## Well Done!")
    lines.append("**Great work — you finished the lesson!**")
    lines.append("")

    return "\n".join(lines)

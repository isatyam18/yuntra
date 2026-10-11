from __future__ import annotations

from html import escape
from pathlib import Path

from .control.learning import LearningRegistry
from .service import ProjectService, git_status


def _rows(items: list[dict], columns: list[str]) -> str:
    if not items:
        return "<p>No records available.</p>"
    header = "".join(
        f"<th>{escape(column.replace('_', ' '))}</th>" for column in columns
    )
    body = "".join(
        "<tr>"
        + "".join(f"<td>{escape(str(item.get(column, '')))}</td>" for column in columns)
        + "</tr>"
        for item in items
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def render_dashboard(project_data: Path, home: Path) -> str:
    """Render a self-contained read-only HTML snapshot from canonical local state."""
    service = ProjectService(home)
    store = service.store(project_data)
    profile = store.profile(service._project_id(project_data))
    events = store.events(profile.project_id)
    decisions = store.decisions(profile.project_id)
    lessons = [
        lesson.model_dump()
        for lesson in LearningRegistry(home).list(profile.project_id)
    ]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Yuntra — {escape(profile.name)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:1100px;margin:2rem auto;color:#17212b}}h1{{margin-bottom:.15rem}}.meta{{color:#52606d}}section{{margin-top:2rem}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.55rem;border-bottom:1px solid #d9e2ec;text-align:left;vertical-align:top}}th{{background:#f0f4f8}}code{{white-space:pre-wrap;display:block;background:#f7f9fb;padding:1rem}}</style>
</head><body><h1>{escape(profile.name)}</h1><p class="meta">Static local snapshot · {escape(profile.project_id)} · state: <strong>{escape(str(profile.state))}</strong></p>
<section><h2>Repository evidence</h2><code>{escape(git_status(Path(profile.repository_path)))}</code></section>
<section><h2>Lifecycle and events</h2>{_rows(events, ["timestamp", "kind", "actor", "from_state", "to_state", "reason"])}</section>
<section><h2>Decisions</h2>{_rows(decisions, ["decision_id", "status", "problem", "chosen_approach", "confidence"])}</section>
<section><h2>Scoped lessons</h2>{_rows(lessons, ["lesson_id", "scope", "status", "description", "confidence"])}</section>
<section><h2>Safety</h2><code>Read-only export. Yuntra did not start a server, collect telemetry, commit, push, or modify the referenced repository.</code></section>
</body></html>"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Annotated

import typer

from .adapters.antigravity import AntigravityAdapter
from .adapters.base import AdapterError
from .adapters.claude_code import ClaudeCodeAdapter
from .adapters.codex import CodexAdapter
from .control.learning import LearningRegistry
from .core.governance import PolicyViolation, require_policy
from .dashboard import render_dashboard
from .memory.context import benchmark_context, build_context
from .models import (
    DecisionRecord,
    LearningScope,
    LifecycleState,
    VerificationStatus,
    utc_now,
)
from .service import (
    ProjectService,
    backup,
    default_home,
    git_status,
    redact,
    restore_backup,
)

app = typer.Typer(help="Yuntra: remember, plan, execute, learn.", no_args_is_help=True)
project_app = typer.Typer(help="Create and inspect centralized project profiles.")
plan_app = typer.Typer(help="Manage the user-authored project plan.")
context_app = typer.Typer(help="Inspect compact working context and context budgets.")
checkpoint_app = typer.Typer(help="Save recovery checkpoints.")
adapter_app = typer.Typer(help="Inspect development-tool adapters.")
codex_app = typer.Typer(help="Use the verified Codex CLI integration.")
claude_app = typer.Typer(help="Use the verified Claude Code CLI integration.")
antigravity_app = typer.Typer(
    help="Use the verified Google Antigravity CLI integration."
)
skills_app = typer.Typer(help="Inspect the local skill registry.")
app.add_typer(project_app, name="project")
app.add_typer(plan_app, name="plan")
app.add_typer(context_app, name="context")
app.add_typer(checkpoint_app, name="checkpoint")
app.add_typer(adapter_app, name="adapter")
app.add_typer(skills_app, name="skills")
adapter_app.add_typer(codex_app, name="codex")
adapter_app.add_typer(claude_app, name="claude-code")
adapter_app.add_typer(antigravity_app, name="antigravity")


def home() -> Path:
    return Path(os.environ.get("YUNTRA_HOME", default_home()))


def data_path(project: str) -> Path:
    path = Path(project)
    if path.exists():
        return path.resolve()
    matches = list((home() / "projects").glob(f"{project}*"))
    if len(matches) == 1:
        return matches[0]
    raise typer.BadParameter(
        "Provide a project data directory or a unique project ID prefix."
    )


@app.command()
def init() -> None:
    """Initialize the centralized Yuntra data directory."""
    root = home()
    (root / "projects").mkdir(parents=True, exist_ok=True)
    (root / "backups").mkdir(exist_ok=True)
    config = root / "config.toml"
    if not config.exists():
        config.write_text(
            "# Yuntra global configuration\n[defaults]\nauto_commit = false\ngit_push = false\n",
            encoding="utf-8",
        )
    typer.echo(f"Initialized Yuntra data directory: {root}")


@project_app.command("create")
def project_create(
    name: Annotated[str, typer.Option(prompt=True)],
    repository: Annotated[Path, typer.Option(exists=True, file_okay=False)],
) -> None:
    """Create a centralized project profile and an editable specification."""
    profile = ProjectService(home()).create(name, repository)
    typer.echo(
        f"Created {profile.project_id}\nData: {profile.data_path}\nSpecification: {Path(profile.data_path) / 'PROJECT_SPEC.md'}"
    )


@project_app.command("inspect")
def project_inspect(project: str) -> None:
    """Show the canonical project profile and its current state."""
    data = data_path(project)
    profile = (
        ProjectService(home())
        .store(data)
        .profile(ProjectService(home())._project_id(data))
    )
    typer.echo(profile.model_dump_json(indent=2))


@plan_app.command("edit")
def plan_edit(project: str) -> None:
    """Print the editable specification location; Yuntra never rewrites approved architecture."""
    typer.echo(data_path(project) / "PROJECT_SPEC.md")


@plan_app.command("review")
def plan_review(project: str) -> None:
    """Validate required manual plan sections without changing implementation files."""
    data = data_path(project)
    try:
        missing = ProjectService(home()).review(data)
    except ValueError as error:
        typer.echo(str(error))
        raise typer.Exit(2) from error
    if missing:
        typer.echo("Plan remains incomplete. Missing content: " + ", ".join(missing))
        raise typer.Exit(2)
    typer.echo("Plan is complete and ready for explicit approval.")


@plan_app.command("approve")
def plan_approve(
    project: str,
    yes: bool = typer.Option(False, "--yes", help="Explicit noninteractive approval."),
) -> None:
    """Explicitly approve a reviewed plan."""
    if not yes and not typer.confirm(
        "Approve this plan and permit implementation work?"
    ):
        raise typer.Abort()
    try:
        profile = ProjectService(home()).approve(data_path(project), "user")
    except ValueError as error:
        typer.echo(str(error))
        raise typer.Exit(2) from error
    typer.echo(f"Plan approved. State: {profile.state}")


@app.command()
def status(project: str) -> None:
    """Show verified profile state and present Git evidence."""
    data = data_path(project)
    service = ProjectService(home())
    profile = service.store(data).profile(service._project_id(data))
    typer.echo(
        f"{profile.name} ({profile.project_id})\nState: {profile.state}\nRepository: {profile.repository_path}\nGit:\n{git_status(Path(profile.repository_path))}"
    )


@context_app.command("show")
def context_show(project: str) -> None:
    """Show compact L1 working context with provenance."""
    result = build_context(data_path(project))
    typer.echo(result["context"])
    typer.echo(
        "\n--- Context manifest ---\n" + json.dumps(result["manifest"], indent=2)
    )


@context_app.command("budget")
def context_budget(
    project: str,
    settings: list[str] = typer.Option(
        [], "--set", help="Set a category budget, e.g. --set documentation=2000."
    ),
) -> None:
    """Show or explicitly configure independent deterministic context budgets."""
    data = data_path(project)
    if settings:
        service = ProjectService(home())
        store = service.store(data)
        profile = store.profile(service._project_id(data))
        for setting in settings:
            key, separator, raw_value = setting.partition("=")
            if not separator or key not in profile.context_budgets:
                raise typer.BadParameter(
                    f"Unknown or malformed budget setting: {setting}"
                )
            try:
                value = int(raw_value)
            except ValueError as error:
                raise typer.BadParameter(
                    f"Budget must be an integer: {setting}"
                ) from error
            if value < 1:
                raise typer.BadParameter("Budget must be greater than zero.")
            profile.context_budgets[key] = value
        store.save_profile(profile)
    result = build_context(data)
    manifest = result["manifest"]
    typer.echo(
        json.dumps(
            {
                "configured_budgets": manifest["budgets"],
                "used_estimated_tokens": manifest["used"],
                "files_or_sections": manifest["files_or_sections"],
                "duplicate_content_removed": manifest["duplicate_content_removed"],
                "omitted": manifest["omitted"],
                "token_estimate": True,
            },
            indent=2,
        )
    )


@context_app.command("retrieve")
def context_retrieve(
    project: str,
    query: str = typer.Option(
        "", help="Task objective or keywords for deterministic ranking."
    ),
    output: Path | None = typer.Option(
        None, help="Optional path for the rendered context."
    ),
) -> None:
    """Retrieve relevant file/section context within configured budgets."""
    result = build_context(data_path(project), query)
    if output:
        output.write_text(result["context"], encoding="utf-8")
        output.with_suffix(output.suffix + ".manifest.json").write_text(
            json.dumps(result["manifest"], indent=2), encoding="utf-8"
        )
        typer.echo(output.resolve())
    else:
        typer.echo(
            result["context"]
            + "\n\n--- Context manifest ---\n"
            + json.dumps(result["manifest"], indent=2)
        )


@context_app.command("benchmark")
def context_benchmark(
    project: str,
    query: str = typer.Option(
        "", help="Task objective or keywords for deterministic ranking."
    ),
) -> None:
    """Report estimated context reduction against a documented local baseline."""
    typer.echo(json.dumps(benchmark_context(data_path(project), query), indent=2))


@checkpoint_app.command("save")
def checkpoint_save(
    project: str, next_action: Annotated[str, typer.Option(prompt=True)]
) -> None:
    """Atomically save a checkpoint containing direct Git evidence."""
    typer.echo(ProjectService(home()).save_checkpoint(data_path(project), next_action))


@app.command()
def resume(project: str) -> None:
    """Load the newest checkpoint and report repository discrepancies."""
    checkpoint, drift = ProjectService(home()).resume(data_path(project))
    typer.echo(checkpoint.model_dump_json(indent=2))
    typer.echo(f"Repository discrepancy detected: {drift}")
    if drift:
        raise typer.Exit(2)


@app.command()
def log(project: str, kind: str | None = None) -> None:
    """List append-only lifecycle, approval, and checkpoint events."""
    data = data_path(project)
    service = ProjectService(home())
    events = service.store(data).events(service._project_id(data), kind)
    typer.echo(json.dumps(events, indent=2))


@app.command()
def decisions(
    project: str,
    problem: str | None = None,
    chosen: str | None = None,
    rationale: str | None = None,
) -> None:
    """List decisions, or record one when --problem, --chosen and --rationale are supplied."""
    data = data_path(project)
    service = ProjectService(home())
    store = service.store(data)
    pid = service._project_id(data)
    if problem or chosen or rationale:
        if problem is None or chosen is None or rationale is None:
            raise typer.BadParameter(
                "Recording a decision requires --problem, --chosen, and --rationale."
            )
        record = DecisionRecord(
            decision_id=f"dec-{uuid.uuid4().hex[:12]}",
            project_id=pid,
            problem=problem,
            chosen_approach=chosen,
            rationale=rationale,
        )
        store.decision(record.model_dump())
        store.event(
            uuid.uuid4().hex, pid, "DECISION", {"decision_id": record.decision_id}
        )
        typer.echo(record.decision_id)
        return
    typer.echo(json.dumps(store.decisions(pid), indent=2))


@app.command()
def verify(
    project: str,
    command: str = typer.Option(
        ..., help="Verification command; passed to the system shell."
    ),
) -> None:
    """Run a user-specified verification command and record its actual result."""
    data = data_path(project)
    service = ProjectService(home())
    store = service.store(data)
    profile = store.profile(service._project_id(data))
    if profile.state not in {
        LifecycleState.APPROVED,
        LifecycleState.EXECUTING,
        LifecycleState.VERIFYING,
    }:
        raise typer.BadParameter("Verification requires an approved plan.")
    result = subprocess.run(
        command,
        cwd=profile.repository_path,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    status_value = (
        VerificationStatus.PASS if result.returncode == 0 else VerificationStatus.FAIL
    )
    record = {
        "verification_id": uuid.uuid4().hex,
        "project_id": profile.project_id,
        "command": redact(command),
        "exit_code": result.returncode,
        "result": status_value,
        "output": redact((result.stdout + result.stderr)[-8000:]),
        "created_at": utc_now(),
    }
    store.verification(record)
    store.event(
        uuid.uuid4().hex,
        profile.project_id,
        "VERIFICATION",
        {"verification_id": record["verification_id"], "result": status_value},
    )
    typer.echo(json.dumps(record, indent=2))
    raise typer.Exit(0 if result.returncode == 0 else 1)


def _export_instructions(adapter, project: str, output: Path | None) -> None:
    text = adapter.export_project_instructions(data_path(project))
    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(output.resolve())
    else:
        typer.echo(text)


def _run_cli_adapter(
    adapter, project: str, prompt: str, yes: bool, confirm_message: str
) -> None:
    if not yes and not typer.confirm(confirm_message):
        raise typer.Abort()
    try:
        result = adapter.run_task(data_path(project), prompt)
    except AdapterError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result, indent=2))
    if result["exit_code"] != 0:
        raise typer.Exit(result["exit_code"])


@adapter_app.command("list")
def adapter_list() -> None:
    """List intentionally conservative adapter capabilities."""
    typer.echo(
        json.dumps(
            [
                CodexAdapter().detect_capabilities(),
                ClaudeCodeAdapter().detect_capabilities(),
                AntigravityAdapter().detect_capabilities(),
            ],
            indent=2,
        )
    )


@adapter_app.command("doctor")
def adapter_doctor() -> None:
    """Run harmless adapter availability checks."""
    for tool, executable in (
        ("codex", "codex"),
        ("claude-code", "claude"),
        ("antigravity", "agy"),
    ):
        typer.echo(f"{tool}: {shutil.which(executable) or 'not found'}")


@codex_app.command("instructions")
def codex_instructions(
    project: str,
    output: Path | None = typer.Option(
        None, help="Optional destination for the generated handoff."
    ),
) -> None:
    """Generate a compact Codex handoff from canonical Yuntra state."""
    _export_instructions(CodexAdapter(), project, output)


@codex_app.command("health")
def codex_health() -> None:
    """Check the installed Codex CLI without invoking an agent."""
    typer.echo(json.dumps(CodexAdapter().health_check(), indent=2))


@codex_app.command("run")
def codex_run(
    project: str,
    prompt: Annotated[str, typer.Option(...)],
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Explicitly authorize launching Codex with workspace-write access.",
    ),
) -> None:
    """Launch a task through `codex exec` after an approved plan and confirmation."""
    _run_cli_adapter(
        CodexAdapter(),
        project,
        prompt,
        yes,
        "Launch Codex with workspace-write access for this approved project?",
    )


@codex_app.command("limitations")
def codex_limitations() -> None:
    typer.echo(json.dumps(CodexAdapter().report_limitations(), indent=2))


@claude_app.command("instructions")
def claude_instructions(project: str, output: Path | None = typer.Option(None)) -> None:
    """Generate a Claude Code handoff from canonical Yuntra state."""
    _export_instructions(ClaudeCodeAdapter(), project, output)


@claude_app.command("health")
def claude_health() -> None:
    """Report Claude Code availability without starting a session."""
    typer.echo(json.dumps(ClaudeCodeAdapter().health_check(), indent=2))


@claude_app.command("run")
def claude_run(
    project: str,
    prompt: Annotated[str, typer.Option(...)],
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Explicitly authorize launching Claude Code for this approved project.",
    ),
) -> None:
    """Launch a task through `claude -p` after an approved plan and confirmation."""
    _run_cli_adapter(
        ClaudeCodeAdapter(),
        project,
        prompt,
        yes,
        "Launch Claude Code for this approved project?",
    )


@claude_app.command("limitations")
def claude_limitations() -> None:
    typer.echo(json.dumps(ClaudeCodeAdapter().report_limitations(), indent=2))


@antigravity_app.command("instructions")
def antigravity_instructions(
    project: str, output: Path | None = typer.Option(None)
) -> None:
    """Generate a Google Antigravity handoff from canonical Yuntra state."""
    _export_instructions(AntigravityAdapter(), project, output)


@antigravity_app.command("health")
def antigravity_health() -> None:
    """Report Google Antigravity availability without starting a session."""
    typer.echo(json.dumps(AntigravityAdapter().health_check(), indent=2))


@antigravity_app.command("run")
def antigravity_run(
    project: str,
    prompt: Annotated[str, typer.Option(...)],
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Explicitly authorize launching Antigravity for this approved project.",
    ),
) -> None:
    """Launch a task through `agy` after an approved plan and confirmation."""
    _run_cli_adapter(
        AntigravityAdapter(),
        project,
        prompt,
        yes,
        "Launch Google Antigravity for this approved project?",
    )


@antigravity_app.command("limitations")
def antigravity_limitations() -> None:
    typer.echo(json.dumps(AntigravityAdapter().report_limitations(), indent=2))


@skills_app.command("list")
def skills_list(project: str | None = None) -> None:
    """List scoped project lessons or globally promoted reusable lessons."""
    project_id = None
    if project:
        data = data_path(project)
        service = ProjectService(home())
        project_id = service._project_id(data)
    lessons = LearningRegistry(home()).list(project_id)
    typer.echo(json.dumps([lesson.model_dump() for lesson in lessons], indent=2))


@skills_app.command("review")
def skills_review(lesson_id: str) -> None:
    """Move an evidence-validated lesson into explicit human review."""
    lesson = LearningRegistry(home()).review(lesson_id)
    typer.echo(lesson.model_dump_json(indent=2))


@skills_app.command("capture")
def skills_capture(
    project: str,
    description: str = typer.Option(...),
    evidence: list[str] = typer.Option(
        ..., help="Repeat for each direct evidence reference."
    ),
    scope: LearningScope = typer.Option(...),
    applicability: str = typer.Option(...),
    confidence: str = typer.Option(...),
) -> None:
    """Capture an evidence-backed candidate lesson; it is not reusable yet."""
    data = data_path(project)
    service = ProjectService(home())
    project_id = service._project_id(data)
    lesson = LearningRegistry(home()).capture(
        project_id, description, evidence, scope, applicability, confidence
    )
    service.store(data).event(
        uuid.uuid4().hex,
        project_id,
        "LEARNING_CAPTURED",
        {"lesson_id": lesson.lesson_id, "scope": scope},
    )
    typer.echo(lesson.model_dump_json(indent=2))


@skills_app.command("validate")
def skills_validate(lesson_id: str) -> None:
    """Validate that a candidate has required evidence and scope metadata."""
    typer.echo(LearningRegistry(home()).validate(lesson_id).model_dump_json(indent=2))


@skills_app.command("promote")
def skills_promote(
    lesson_id: str,
    yes: bool = typer.Option(
        False, "--yes", help="Explicitly approve promotion after review."
    ),
) -> None:
    """Promote a reviewed lesson; this always requires human confirmation."""
    if not yes and not typer.confirm("Promote this reviewed lesson for future reuse?"):
        raise typer.Abort()
    typer.echo(LearningRegistry(home()).promote(lesson_id).model_dump_json(indent=2))


@skills_app.command("evaluate")
def skills_evaluate(lesson_id: str, outcome: str = typer.Option(...)) -> None:
    """Record observed usefulness/limitations of a promoted lesson."""
    typer.echo(
        LearningRegistry(home()).evaluate(lesson_id, outcome).model_dump_json(indent=2)
    )


@app.command()
def doctor() -> None:
    """Report local runtime prerequisites."""
    typer.echo(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "git": bool(shutil.which("git")),
                "codex": bool(shutil.which("codex")),
                "data_home": str(home()),
            },
            indent=2,
        )
    )


@app.command()
def dashboard(
    project: str,
    output: Path | None = typer.Option(
        None, help="Destination HTML file; defaults to the project data directory."
    ),
) -> None:
    """Export a read-only, self-contained local HTML project snapshot."""
    data = data_path(project)
    destination = output or (data / "dashboard.html")
    destination.write_text(render_dashboard(data, home()), encoding="utf-8")
    typer.echo(destination.resolve())


@app.command("backup")
def backup_project(project: str, destination: Path | None = None) -> None:
    """Create a timestamped archive of only this project's canonical state."""
    data = data_path(project)
    typer.echo(backup(data, destination or (home() / "backups")))


@app.command()
def restore(
    archive: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    destination: Annotated[Path, typer.Option()],
) -> None:
    """Restore an archive only into a new empty destination, never over existing work."""
    try:
        restore_backup(archive, destination)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Restored archive contents: {destination}")


@app.command()
def policy(project: str, operation: str) -> None:
    """Check whether a configured high-risk operation is permitted."""
    data = data_path(project)
    service = ProjectService(home())
    profile = service.store(data).profile(service._project_id(data))
    try:
        require_policy(profile, operation)
    except PolicyViolation as error:
        typer.echo(str(error))
        raise typer.Exit(2)
    typer.echo(f"Policy permits {operation}.")


@app.command()
def export(
    project: str, destination: Path = typer.Option(Path("yuntra-export.jsonl"))
) -> None:
    """Export portable append-only event records."""
    data = data_path(project)
    source = data / "events.jsonl"
    if not source.exists():
        raise typer.BadParameter("No events are available to export.")
    shutil.copyfile(source, destination)
    typer.echo(destination.resolve())


if __name__ == "__main__":
    app()

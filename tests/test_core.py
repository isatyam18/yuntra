import subprocess
from pathlib import Path

import pytest

from yuntra.adapters.antigravity import AntigravityAdapter
from yuntra.adapters.base import AdapterError
from yuntra.adapters.claude_code import ClaudeCodeAdapter
from yuntra.adapters.codex import CodexAdapter
from yuntra.control.learning import LearningRegistry
from yuntra.core.governance import PolicyViolation, require_policy
from yuntra.dashboard import render_dashboard
from yuntra.diagram import (
    ARCHIFY_REPO,
    archify_health,
    build_cache_aside_spec,
    list_diagrams,
)
from yuntra.memory.context import benchmark_context, build_context
from yuntra.models import LearningScope, LearningStatus, LifecycleState
from yuntra.security import redact_payload
from yuntra.service import (
    ProjectService,
    backup,
    check_spec_drift,
    get_approved_spec,
    redact,
    restore_backup,
)
from yuntra.store import Store


@pytest.fixture()
def project(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    service = ProjectService(tmp_path / "yuntra-data")
    profile = service.create("Demo", repo)
    return service, Path(profile.data_path), profile


def complete_spec(data: Path) -> None:
    path = data / "PROJECT_SPEC.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "<!-- Complete this section yourself. AI suggestions must be labeled. -->",
            "User supplied content.",
        ),
        encoding="utf-8",
    )


def test_cannot_approve_incomplete_plan(project):
    service, data, _ = project
    with pytest.raises(ValueError, match="incomplete"):
        service.approve(data, "user")


def test_valid_approval_preserves_spec(project):
    service, data, _ = project
    complete_spec(data)
    original = (data / "PROJECT_SPEC.md").read_text(encoding="utf-8")
    assert service.review(data) == []
    assert service.approve(data, "user").state is LifecycleState.APPROVED
    assert (data / "PROJECT_SPEC.md").read_text(encoding="utf-8") == original


def test_invalid_transition_rejected(project):
    service, data, _ = project
    with pytest.raises(ValueError, match="Invalid lifecycle"):
        service.transition(data, LifecycleState.COMPLETED, "skip")


def test_checkpoint_detects_repository_drift(project):
    service, data, profile = project
    path = service.save_checkpoint(data, "Review plan")
    assert path.exists()
    (Path(profile.repository_path) / "untracked.txt").write_text(
        "changed", encoding="utf-8"
    )
    _, drift = service.resume(data)
    assert drift


def test_projects_are_isolated(tmp_path: Path):
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    subprocess.run(["git", "init"], cwd=repo_a, check=True, capture_output=True)
    subprocess.run(["git", "init"], cwd=repo_b, check=True, capture_output=True)
    service = ProjectService(tmp_path / "data")
    a = service.create("A", repo_a)
    b = service.create("B", repo_b)
    assert a.project_id != b.project_id
    assert Path(a.data_path) != Path(b.data_path)
    assert "A Project" in (Path(a.data_path) / "PROJECT_SPEC.md").read_text(
        encoding="utf-8"
    )
    assert "A Project" not in (Path(b.data_path) / "PROJECT_SPEC.md").read_text(
        encoding="utf-8"
    )


def test_safe_defaults_and_changelog(project):
    _service, data, profile = project
    assert profile.policies["allow_auto_commit"] is False
    assert profile.policies["allow_git_push"] is False
    assert "PROJECT_CREATED" in (data / "CHANGELOG.md").read_text(encoding="utf-8")


def test_sensitive_assignments_are_redacted():
    assert "[REDACTED]" in redact("API_KEY=top-secret-value")


def test_codex_handoff_uses_canonical_spec(project):
    service, data, profile = project
    complete_spec(data)
    service.review(data)
    service.approve(data, "user")
    handoff = CodexAdapter().export_project_instructions(data)
    assert profile.project_id in handoff
    assert "Do not commit, push" in handoff
    assert "User supplied content." in handoff


def test_codex_run_requires_approval(project, monkeypatch):
    _, data, _ = project
    monkeypatch.setattr("yuntra.adapters.codex.shutil.which", lambda _: "codex")
    with pytest.raises(Exception, match="requires APPROVED"):
        CodexAdapter().run_task(data, "do something")


def test_codex_run_records_adapter_report(project, monkeypatch):
    service, data, profile = project
    complete_spec(data)
    service.review(data)
    service.approve(data, "user")
    monkeypatch.setattr("yuntra.adapters.codex.shutil.which", lambda _: "codex")
    original_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if command[0] == "codex":
            return subprocess.CompletedProcess(command, 0, '{"type":"completed"}', "")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr("yuntra.adapters.codex.subprocess.run", fake_run)
    result = CodexAdapter().run_task(data, "inspect implementation")
    assert result["exit_code"] == 0
    assert (
        service.store(data).profile(profile.project_id).state
        is LifecycleState.EXECUTING
    )
    assert (data / "codex-handoff.md").exists()
    assert any(
        event["kind"] == "ADAPTER_RUN"
        for event in service.store(data).events(profile.project_id)
    )


@pytest.mark.parametrize("adapter", [ClaudeCodeAdapter(), AntigravityAdapter()])
def test_adapters_export_canonical_handoff(project, adapter):
    service, data, profile = project
    complete_spec(data)
    service.review(data)
    service.approve(data, "user")
    handoff = adapter.export_project_instructions(data)
    assert profile.project_id in handoff
    assert "Do not commit, push" in handoff
    assert "User supplied content." in handoff
    capabilities = adapter.detect_capabilities()
    assert capabilities["name"] == adapter.name
    assert "CLI health check" in capabilities["supported"]


@pytest.mark.parametrize("adapter", [ClaudeCodeAdapter(), AntigravityAdapter()])
def test_adapters_run_requires_approval(project, adapter, monkeypatch):
    _, data, _ = project
    executable_name = "claude" if adapter.name == "claude-code" else "agy"
    module_path = f"yuntra.adapters.{'claude_code' if adapter.name == 'claude-code' else 'antigravity'}.shutil.which"
    monkeypatch.setattr(module_path, lambda _: executable_name)
    with pytest.raises(Exception, match="requires APPROVED"):
        adapter.run_task(data, "do something")


@pytest.mark.parametrize(
    "adapter_cls,executable,module",
    [
        (ClaudeCodeAdapter, "claude", "yuntra.adapters.claude_code"),
        (AntigravityAdapter, "agy", "yuntra.adapters.antigravity"),
    ],
)
def test_adapters_run_records_adapter_report(
    project, monkeypatch, adapter_cls, executable, module
):
    service, data, profile = project
    complete_spec(data)
    service.review(data)
    service.approve(data, "user")
    monkeypatch.setattr(f"{module}.shutil.which", lambda _: executable)
    original_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if command[0] == executable:
            return subprocess.CompletedProcess(command, 0, '{"type":"completed"}', "")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(f"{module}.subprocess.run", fake_run)
    adapter = adapter_cls()
    result = adapter.run_task(data, "inspect implementation")
    assert result["exit_code"] == 0
    assert (
        service.store(data).profile(profile.project_id).state
        is LifecycleState.EXECUTING
    )
    handoff_name = f"{adapter.name}-handoff.md"
    assert (data / handoff_name).exists()
    assert any(
        event["kind"] == "ADAPTER_RUN"
        for event in service.store(data).events(profile.project_id)
    )


def test_context_retrieval_excludes_secrets_and_reduces_duplicates(project):
    _service, data, profile = project
    repository = Path(profile.repository_path)
    (repository / "auth.md").write_text(
        "# Authentication\nUse explicit error handling.", encoding="utf-8"
    )
    (repository / "duplicate.md").write_text(
        "# Authentication\nUse explicit error handling.", encoding="utf-8"
    )
    (repository / ".env").write_text("API_KEY=not-for-context", encoding="utf-8")
    result = build_context(data, "authentication error")
    paths = [item["path"] for item in result["manifest"]["items"]]
    assert ".env" not in paths
    assert result["manifest"]["duplicate_content_removed"] >= 1
    assert any("auth.md" in path or "duplicate.md" in path for path in paths)


def test_context_benchmark_is_explicitly_estimated(project):
    _, data, profile = project
    (Path(profile.repository_path) / "feature.py").write_text(
        "def feature():\n    return 'context retrieval'\n", encoding="utf-8"
    )
    benchmark = benchmark_context(data, "context retrieval")
    assert benchmark["token_estimate"] is True
    assert "Baseline is every eligible" in benchmark["methodology"]


def test_learning_requires_evidence_and_explicit_gates(tmp_path: Path):
    registry = LearningRegistry(tmp_path)
    lesson = registry.capture(
        "project-a",
        "Use a focused regression test after a verified fix.",
        ["verification-123"],
        LearningScope.GLOBAL,
        "Python projects with regression coverage",
        "medium",
    )
    assert registry.list() == []
    assert registry.validate(lesson.lesson_id).status is LearningStatus.VALIDATED
    assert registry.review(lesson.lesson_id).status is LearningStatus.REVIEW
    assert registry.promote(lesson.lesson_id).status is LearningStatus.PROMOTED
    assert registry.list()[0].lesson_id == lesson.lesson_id


def test_learning_deduplicates_and_does_not_leak_project_candidates(tmp_path: Path):
    registry = LearningRegistry(tmp_path)
    lesson = registry.capture(
        "project-a",
        "Handle errors explicitly",
        ["event-1"],
        LearningScope.PROJECT,
        "CLI work",
        "high",
    )
    assert registry.list() == []
    with pytest.raises(ValueError, match="Duplicate"):
        registry.capture(
            "project-b",
            "Handle errors explicitly",
            ["event-2"],
            LearningScope.PROJECT,
            "CLI work",
            "high",
        )
    assert registry.list("project-b") == []
    assert registry.list("project-a")[0].lesson_id == lesson.lesson_id


def test_schema_version_and_existing_profile_survive_reopen(project):
    _service, data, profile = project
    assert Store(data).schema_version() == 1
    assert Store(data).profile(profile.project_id).name == "Demo"


def test_restore_refuses_overwrite_and_preserves_archive_contents(
    project, tmp_path: Path
):
    _, data, _ = project
    archive = backup(data, tmp_path / "backups")
    destination = tmp_path / "restored"
    restore_backup(archive, destination)
    assert list(destination.rglob("PROJECT_SPEC.md"))
    with pytest.raises(ValueError, match="already exists"):
        restore_backup(archive, destination)


def test_policy_defaults_block_high_risk_operations(project):
    _, _, profile = project
    with pytest.raises(PolicyViolation, match="git_push"):
        require_policy(profile, "git_push")


def test_resume_ignores_interrupted_checkpoint_temporary_file(project):
    service, data, _ = project
    saved = service.save_checkpoint(data, "Continue safely")
    saved.with_suffix(".tmp").write_text("not valid JSON", encoding="utf-8")
    checkpoint, _ = service.resume(data)
    assert checkpoint.next_action == "Continue safely"


def test_dashboard_is_static_and_escapes_project_data(project):
    service, data, profile = project
    service.store(data).event(
        "event-dashboard", profile.project_id, "NOTE", {"actor": "<untrusted>"}
    )
    html = render_dashboard(data, service.home)
    assert "Static local snapshot" in html
    assert "&lt;untrusted&gt;" in html
    assert "did not start a server" in html


def test_sensitive_data_is_redacted_before_persistence(project):
    service, data, profile = project
    service.store(data).event(
        "event-secret",
        profile.project_id,
        "NOTE",
        {"detail": "Authorization: Bearer keep-me-secret"},
    )
    persisted = service.store(data).events(profile.project_id)[-1]
    assert "keep-me-secret" not in persisted["detail"]
    assert "[REDACTED]" in persisted["detail"]
    assert redact_payload({"token": "token=abc"})["token"] == "token=[REDACTED]"


def test_review_rejects_sensitive_specification(project):
    service, data, _ = project
    path = data / "PROJECT_SPEC.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\npassword = unsafe-value\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sensitive values"):
        service.review(data)


def test_record_change_auto_logs_with_reason(project):
    service, data, profile = project
    (Path(profile.repository_path) / "feature.py").write_text(
        "print('feature')", encoding="utf-8"
    )
    record = service.record_change(data, "Implemented user authentication feature")
    assert record["reason"] == "Implemented user authentication feature"
    assert "feature.py" in record["observed_after"]
    events = service.store(data).events(profile.project_id)
    change_events = [e for e in events if e.get("kind") == "CHANGE_OBSERVED"]
    assert len(change_events) >= 1
    assert change_events[-1]["reason"] == "Implemented user authentication feature"
    changelog = (data / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "CHANGE_OBSERVED: Implemented user authentication feature" in changelog


def test_plan_approval_records_revision_snapshot(project):
    service, data, _ = project
    complete_spec(data)
    service.review(data)
    service.approve(data, "user")
    revisions = list((data / "revisions").glob("spec-*.md"))
    assert len(revisions) == 1
    assert "User supplied content." in revisions[0].read_text(encoding="utf-8")


def test_archify_health_structure():
    status = archify_health()
    assert "healthy" in status
    assert status["repo"] == ARCHIFY_REPO


def test_build_cache_aside_spec():
    spec = build_cache_aside_spec(".archify/test/test.html", "Test Sequence")
    assert spec["schema_version"] == 1
    assert spec["diagram_type"] == "sequence"
    assert spec["meta"]["title"] == "Test Sequence"
    participant_ids = [p["id"] for p in spec["participants"]]
    assert "browser" in participant_ids
    assert "api" in participant_ids
    assert "redis" in participant_ids
    assert "postgres" in participant_ids
    message_ids = [m["id"] for m in spec["messages"]]
    assert "http-request" in message_ids
    assert "cache-miss" in message_ids


def test_list_diagrams(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert list_diagrams(repo) == []

    diagram_dir = repo / ".archify" / "test-diagram"
    diagram_dir.mkdir(parents=True)
    html_file = diagram_dir / "test-diagram.html"
    html_file.write_text(
        "<html><body>Interactive diagram</body></html>", encoding="utf-8"
    )

    candidate = diagram_dir / "candidate.json"
    candidate.write_text(
        '{"meta": {"title": "Sample Diagram"}, "diagram_type": "sequence"}',
        encoding="utf-8",
    )

    diagrams = list_diagrams(repo)
    assert len(diagrams) == 1
    assert diagrams[0]["title"] == "Sample Diagram"
    assert diagrams[0]["type"] == "sequence"
    assert "test-diagram.html" in diagrams[0]["relative_path"]


def test_spec_drift_detection_and_handoff_isolation(project, monkeypatch):
    service, data, _ = project
    complete_spec(data)
    service.review(data)
    approved_profile = service.approve(data, "user")
    assert approved_profile.approved_spec_hash is not None
    assert approved_profile.approved_spec_revision is not None

    # Verify no drift initially
    drifted, app_h, live_h = check_spec_drift(data)
    assert not drifted
    assert app_h == live_h

    # Modify live spec post-approval
    spec_path = data / "PROJECT_SPEC.md"
    original_spec = spec_path.read_text(encoding="utf-8")
    spec_path.write_text(original_spec + "\n<!-- Unapproved post-approval modification -->", encoding="utf-8")

    # Drift must now be detected
    drifted, app_h, live_h = check_spec_drift(data)
    assert drifted
    assert app_h != live_h

    # Handoff export and get_approved_spec MUST use the approved snapshot, not the drifted live file
    adapter = CodexAdapter()
    handoff_text = adapter.export_project_instructions(data)
    assert "Unapproved post-approval modification" not in handoff_text
    assert "User supplied content." in handoff_text
    assert "Unapproved post-approval modification" not in get_approved_spec(data)
    assert "User supplied content." in get_approved_spec(data)

    # Mock CLI availability and check that run_task blocks execution and reverts state to REVIEW
    monkeypatch.setattr("shutil.which", lambda _: "/mock/codex")
    with pytest.raises(AdapterError, match="Specification has been modified after approval"):
        adapter.run_task(data, "Do work")

    # State should have reverted to REVIEW
    current_profile = service.store(data).profile(approved_profile.project_id)
    assert current_profile.state == LifecycleState.REVIEW


def test_adapter_policy_enforcement(project):
    _service, data, profile = project

    claude = ClaudeCodeAdapter()
    # Default policies: allow_destructive_operations and allow_dependency_install are False
    cmd_default, _ = claude._build_command("claude", profile.repository_path, data / "handoff.md", "task", profile)
    allowed_idx = cmd_default.index("--allowedTools")
    assert cmd_default[allowed_idx + 1] == "Read,Edit"
    assert "Bash" not in cmd_default[allowed_idx + 1]

    # Enabled policies: allow_destructive_operations=True
    profile.policies["allow_destructive_operations"] = True
    cmd_enabled, _ = claude._build_command("claude", profile.repository_path, data / "handoff.md", "task", profile)
    allowed_idx2 = cmd_enabled.index("--allowedTools")
    assert "Bash" in cmd_enabled[allowed_idx2 + 1]

    agy = AntigravityAdapter()
    # Without policy: no --dangerously-skip-permissions
    profile.policies["allow_destructive_operations"] = False
    cmd_agy, _ = agy._build_command("agy", profile.repository_path, data / "handoff.md", "task", profile)
    assert "--dangerously-skip-permissions" not in cmd_agy

    # With policy: --dangerously-skip-permissions present
    profile.policies["allow_destructive_operations"] = True
    cmd_agy_optin, _ = agy._build_command("agy", profile.repository_path, data / "handoff.md", "task", profile)
    assert "--dangerously-skip-permissions" in cmd_agy_optin


def test_restore_backup_rejects_path_traversal(tmp_path: Path):
    import zipfile

    # Create malicious archive with path traversal (Zip Slip)
    archive_path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("../evil.txt", "exploit")

    target_dir = tmp_path / "restored"
    with pytest.raises(ValueError, match="Archive contains an unsafe path."):
        restore_backup(archive_path, target_dir)

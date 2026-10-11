from pathlib import Path
import subprocess

import pytest

from yuntra.models import LifecycleState
from yuntra.service import ProjectService, redact
from yuntra.adapters.codex import CodexAdapter
from yuntra.adapters.claude_code import ClaudeCodeAdapter
from yuntra.adapters.antigravity import AntigravityAdapter
from yuntra.memory.context import benchmark_context, build_context
from yuntra.control.learning import LearningRegistry
from yuntra.models import LearningScope, LearningStatus
from yuntra.store import Store
from yuntra.service import backup, restore_backup
from yuntra.core.governance import PolicyViolation, require_policy
from yuntra.dashboard import render_dashboard
from yuntra.security import redact_payload


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
    service, data, profile = project
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
def test_manual_adapters_export_canonical_handoff_and_refuse_runs(project, adapter):
    service, data, profile = project
    complete_spec(data)
    service.review(data)
    service.approve(data, "user")
    assert profile.project_id in adapter.export_project_instructions(data)
    assert adapter.detect_capabilities()["fallback"]
    with pytest.raises(Exception, match="automation is not verified"):
        adapter.run_task(data, "implement")


def test_context_retrieval_excludes_secrets_and_reduces_duplicates(project):
    service, data, profile = project
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
    service, data, profile = project
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

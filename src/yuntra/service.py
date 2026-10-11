from __future__ import annotations

import os
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

from .lifecycle import can_transition
from .models import Checkpoint, LifecycleState, ProjectProfile, utc_now
from .security import redact_text, sensitive_markers
from .store import Store

REQUIRED_SECTIONS = [
    "Project name",
    "Problem statement",
    "Primary goal",
    "Architecture",
    "Component interfaces",
    "Execution plan",
    "Required skills",
    "Operating environment",
    "Constraints",
    "Acceptance criteria",
    "Risks",
    "Out of scope",
]


def default_home() -> Path:
    return (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        / "Yuntra"
    )


def project_dir(home: Path, project_id: str) -> Path:
    return home / "projects" / project_id


def new_id(name: str) -> str:
    safe = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    return f"{safe}-{uuid.uuid4().hex[:8]}"


def spec_template(name: str) -> str:
    headings = "\n\n".join(
        f"## {heading}\n<!-- Complete this section yourself. AI suggestions must be labeled. -->"
        for heading in REQUIRED_SECTIONS
    )
    return f"# {name} Project Specification\n\nStatus: Draft\n\n{headings}\n"


class ProjectService:
    def __init__(self, home: Path):
        self.home = home

    def create(self, name: str, repository: Path) -> ProjectProfile:
        repository = repository.resolve()
        if not repository.exists():
            raise ValueError(f"Repository path does not exist: {repository}")
        project_id = new_id(name)
        data = project_dir(self.home, project_id)
        data.mkdir(parents=True)
        profile = ProjectProfile(
            project_id=project_id,
            name=name,
            repository_path=str(repository),
            data_path=str(data),
        )
        Store(data).save_profile(profile)
        (data / "PROJECT_SPEC.md").write_text(spec_template(name), encoding="utf-8")
        Store(data).event(
            uuid.uuid4().hex,
            project_id,
            "PROJECT_CREATED",
            {"actor": "user", "repository_path": str(repository)},
        )
        return profile

    def store(self, data: Path) -> Store:
        return Store(data)

    def transition(
        self, data: Path, target: LifecycleState, reason: str, actor: str = "user"
    ) -> ProjectProfile:
        store = self.store(data)
        profile = store.profile(self._project_id(data))
        if not can_transition(profile.state, target):
            raise ValueError(
                f"Invalid lifecycle transition: {profile.state} -> {target}"
            )
        before = profile.state
        profile.state = target
        store.save_profile(profile)
        store.event(
            uuid.uuid4().hex,
            profile.project_id,
            "LIFECYCLE",
            {
                "from_state": before,
                "to_state": target,
                "reason": reason,
                "actor": actor,
            },
        )
        return profile

    def review(self, data: Path) -> list[str]:
        profile = self.store(data).profile(self._project_id(data))
        if profile.state == LifecycleState.NEW:
            self.transition(data, LifecycleState.PLANNING, "Planning started")
        text = (data / "PROJECT_SPEC.md").read_text(encoding="utf-8")
        markers = sensitive_markers(text)
        if markers:
            raise ValueError(
                "Specification appears to contain sensitive values ("
                + ", ".join(sorted(set(markers)))
                + "). Remove them before review or approval."
            )
        missing = [
            section
            for section in REQUIRED_SECTIONS
            if f"## {section}" not in text
            or "<!-- Complete this section yourself. AI suggestions must be labeled. -->"
            in text.split(f"## {section}", 1)[1].split("##", 1)[0]
        ]
        profile = self.store(data).profile(self._project_id(data))
        if not missing and profile.state == LifecycleState.PLANNING:
            self.transition(
                data, LifecycleState.REVIEW, "Required specification sections completed"
            )
        return missing

    def approve(self, data: Path, actor: str) -> ProjectProfile:
        missing = self.review(data)
        if missing:
            raise ValueError(
                "Cannot approve an incomplete specification: " + ", ".join(missing)
            )
        profile = self.store(data).profile(self._project_id(data))
        if profile.state != LifecycleState.REVIEW:
            raise ValueError(
                f"Plan must be in REVIEW, current state is {profile.state}"
            )
        approved = self.transition(
            data, LifecycleState.APPROVED, "Plan explicitly approved", actor
        )
        self.store(data).event(
            uuid.uuid4().hex,
            approved.project_id,
            "APPROVAL",
            {"actor": actor, "approval": "plan"},
        )
        return approved

    def save_checkpoint(self, data: Path, next_action: str) -> Path:
        profile = self.store(data).profile(self._project_id(data))
        checkpoint = Checkpoint(
            project_id=profile.project_id,
            lifecycle_state=profile.state,
            next_action=redact_text(next_action),
            git_status=git_status(Path(profile.repository_path)),
        )
        folder = data / "checkpoints"
        folder.mkdir(exist_ok=True)
        final = folder / f"{checkpoint.created_at.replace(':', '-')}.json"
        temp = final.with_suffix(".tmp")
        temp.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
        temp.replace(final)
        self.store(data).event(
            uuid.uuid4().hex,
            profile.project_id,
            "CHECKPOINT",
            {"path": str(final), "next_action": next_action},
        )
        return final

    def resume(self, data: Path) -> tuple[Checkpoint, bool]:
        files = (
            sorted((data / "checkpoints").glob("*.json"))
            if (data / "checkpoints").exists()
            else []
        )
        if not files:
            raise ValueError("No checkpoints exist for this project")
        checkpoint = Checkpoint.model_validate_json(
            files[-1].read_text(encoding="utf-8")
        )
        profile = self.store(data).profile(self._project_id(data))
        return checkpoint, checkpoint.git_status != git_status(
            Path(profile.repository_path)
        )

    def _project_id(self, data: Path) -> str:
        with Store(data)._connect() as con:
            row = con.execute("SELECT project_id FROM profiles LIMIT 1").fetchone()
        if not row:
            raise KeyError(f"No project profile in {data}")
        return row["project_id"]


def git_status(repository: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "status", "--short", "--branch"],
        text=True,
        capture_output=True,
        check=False,
    )
    return (
        result.stdout.strip()
        if result.returncode == 0
        else f"Git unavailable: {result.stderr.strip()}"
    )


def redact(text: str) -> str:
    """Backward-compatible public redaction helper."""
    return redact_text(text)


def backup(data: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{data.name}-{utc_now().replace(':', '-')}.zip"
    return Path(
        shutil.make_archive(str(target.with_suffix("")), "zip", data.parent, data.name)
    )


def restore_backup(archive: Path, destination: Path) -> None:
    """Safely extract a Yuntra archive into a new empty directory only."""
    if destination.exists():
        raise ValueError(
            "Restore destination already exists; refusing to overwrite work."
        )
    with zipfile.ZipFile(archive) as bundle:
        target_root = destination.resolve()
        for member in bundle.infolist():
            target = (target_root / member.filename).resolve()
            if target != target_root and target_root not in target.parents:
                raise ValueError("Archive contains an unsafe path.")
        destination.mkdir(parents=True)
        bundle.extractall(destination)

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from yuntra.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Yuntra: remember, plan, execute, learn." in result.stdout


def test_cli_lifecycle_happy_path(tmp_path: Path, monkeypatch):
    # Set YUNTRA_HOME to a temporary directory
    home_dir = tmp_path / "yuntra_home"
    monkeypatch.setenv("YUNTRA_HOME", str(home_dir))

    # Create dummy git repository
    repo_dir = tmp_path / "dummy_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)

    # 1. Init
    res = runner.invoke(app, ["init"])
    assert res.exit_code == 0
    assert "Initialized Yuntra data directory" in res.stdout

    # 2. Project create
    res = runner.invoke(
        app,
        ["project", "create", "--name", "test-project", "--repository", str(repo_dir)],
    )
    assert res.exit_code == 0
    match = re.search(r"Created ([^\s\n]+)", res.stdout)
    assert match is not None
    project_id = match.group(1)

    # 3. Plan review - incomplete template initially returns exit code 2
    res = runner.invoke(app, ["plan", "review", project_id])
    assert res.exit_code == 2
    assert "Plan remains incomplete" in res.stdout

    # Fill out the required specification sections
    project_data = home_dir / "projects" / project_id
    spec_file = project_data / "PROJECT_SPEC.md"
    content = spec_file.read_text(encoding="utf-8").replace(
        "<!-- Complete this section yourself. AI suggestions must be labeled. -->",
        "Completed section content.",
    )
    spec_file.write_text(content, encoding="utf-8")

    # 4. Plan review - complete
    res = runner.invoke(app, ["plan", "review", project_id])
    assert res.exit_code == 0
    assert "Plan is complete and ready for explicit approval" in res.stdout

    # 5. Plan approve (with --yes for noninteractive confirmation)
    res = runner.invoke(app, ["plan", "approve", project_id, "--yes"])
    assert res.exit_code == 0
    assert "APPROVED" in res.stdout

    # 6. Verify command (PASS)
    res = runner.invoke(app, ["verify", project_id, "--command", "git status"])
    assert res.exit_code == 0
    assert '"result": "PASS"' in res.stdout

    # 7. Checkpoint save
    res = runner.invoke(
        app, ["checkpoint", "save", project_id, "--next-action", "Deploy to staging"]
    )
    assert res.exit_code == 0

    # 8. Resume checkpoint
    res = runner.invoke(app, ["resume", project_id])
    assert res.exit_code == 0
    assert "Deploy to staging" in res.stdout

    # 9. Record and list decisions
    res = runner.invoke(
        app,
        [
            "decisions",
            project_id,
            "--problem",
            "State persistence",
            "--chosen",
            "SQLite + WAL",
            "--rationale",
            "Single file, zero external deps, atomic transactions",
        ],
    )
    assert res.exit_code == 0
    assert "dec-" in res.stdout

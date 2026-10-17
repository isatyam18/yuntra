from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ARCHIFY_REPO = "https://github.com/tt-a1i/archify"


def find_archify_command() -> tuple[list[str], str | None]:
    """Locate the Archify executable or runner script.

    Archify repository reference: https://github.com/tt-a1i/archify
    """
    mod = sys.modules.get(__name__)
    which_fn = getattr(getattr(mod, "shutil", None), "which", shutil.which)

    direct = which_fn("archify")
    if direct:
        return [direct], direct

    # Check Windows cmd shim
    direct_cmd = which_fn("archify.cmd")
    if direct_cmd:
        return [direct_cmd], direct_cmd

    node = which_fn("node")
    if node:
        home_dir = Path.home()
        candidates = [
            home_dir / ".agents" / "skills" / "archify" / "bin" / "archify.mjs",
            home_dir
            / ".gemini"
            / "config"
            / "plugins"
            / "archify"
            / "bin"
            / "archify.mjs",
            home_dir
            / ".gemini"
            / "antigravity-ide"
            / "builtin"
            / "skills"
            / "archify"
            / "bin"
            / "archify.mjs",
        ]
        for candidate in candidates:
            if candidate.exists():
                return [node, str(candidate)], str(candidate)

    return [], None


def archify_health() -> dict[str, Any]:
    """Check Archify availability and installation health."""
    cmd_prefix, path = find_archify_command()
    if not cmd_prefix:
        return {
            "healthy": False,
            "executable": None,
            "reason": (
                "Archify CLI not found. Install via 'npx skills add tt-a1i/archify -g'. "
                f"Reference: {ARCHIFY_REPO}"
            ),
            "repo": ARCHIFY_REPO,
        }

    try:
        res = subprocess.run(
            [*cmd_prefix, "doctor"],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        return {
            "healthy": res.returncode == 0,
            "executable": path,
            "output": res.stdout.strip(),
            "error": res.stderr.strip() if res.returncode != 0 else None,
            "repo": ARCHIFY_REPO,
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {
            "healthy": False,
            "executable": path,
            "reason": str(exc),
            "repo": ARCHIFY_REPO,
        }


def list_diagrams(repo_path: Path) -> list[dict[str, Any]]:
    """List interactive diagrams found under .archify in the repository."""
    archify_dir = repo_path / ".archify"
    if not archify_dir.exists():
        return []

    diagrams: list[dict[str, Any]] = []
    for html_file in sorted(archify_dir.rglob("*.html")):
        candidate_file = html_file.parent / "candidate.json"
        delivery_file = html_file.parent / f"{html_file.stem}.delivery.json"
        title = html_file.stem.replace("-", " ").title()
        diagram_type = "sequence"

        if candidate_file.exists():
            try:
                candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
                title = candidate_data.get("meta", {}).get("title", title)
                diagram_type = candidate_data.get("diagram_type", diagram_type)
            except (json.JSONDecodeError, OSError):
                title = html_file.stem.replace("-", " ").title()

        diagrams.append(
            {
                "title": title,
                "type": diagram_type,
                "path": str(html_file.resolve()),
                "relative_path": str(html_file.relative_to(repo_path)),
                "size_bytes": html_file.stat().st_size,
                "has_candidate": candidate_file.exists(),
                "has_delivery": delivery_file.exists(),
            }
        )
    return diagrams


def build_cache_aside_spec(
    output_html_rel: str,
    title: str = "Web Request: Cache Miss and Database Fallback",
) -> dict[str, Any]:
    """Generate a standard candidate specification for cache-aside request architecture."""
    return {
        "schema_version": 1,
        "diagram_type": "sequence",
        "meta": {
            "title": title,
            "output": output_html_rel,
            "locale": "en",
            "quality_profile": "showcase",
        },
        "participants": [
            {
                "id": "browser",
                "type": "external",
                "label": "Browser",
                "sublabel": "client session",
            },
            {
                "id": "api",
                "type": "backend",
                "label": "API",
                "sublabel": "request handler",
            },
            {
                "id": "redis",
                "type": "database",
                "label": "Redis",
                "sublabel": "in-memory cache",
            },
            {
                "id": "postgres",
                "type": "database",
                "label": "PostgreSQL",
                "sublabel": "primary database",
            },
        ],
        "segments": [
            {"from": 150, "to": 265, "label": "Cache Lookup"},
            {"from": 275, "to": 405, "label": "Database Fallback & Cache Fill"},
            {"from": 415, "to": 465, "label": "Response"},
        ],
        "messages": [
            {
                "id": "http-request",
                "from": "browser",
                "to": "api",
                "y": 165,
                "label": "GET /api/resource",
                "variant": "emphasis",
            },
            {
                "id": "cache-lookup",
                "from": "api",
                "to": "redis",
                "y": 200,
                "label": "GET cache:key",
                "variant": "default",
            },
            {
                "id": "cache-miss",
                "from": "redis",
                "to": "api",
                "y": 235,
                "label": "(nil) cache miss",
                "variant": "return",
            },
            {
                "id": "db-query",
                "from": "api",
                "to": "postgres",
                "y": 290,
                "label": "SELECT * FROM resource WHERE id = ?",
                "variant": "emphasis",
            },
            {
                "id": "db-result",
                "from": "postgres",
                "to": "api",
                "y": 325,
                "label": "row data",
                "variant": "return",
            },
            {
                "id": "cache-fill",
                "from": "api",
                "to": "redis",
                "y": 365,
                "label": "SETEX cache:key 3600 data",
                "variant": "dashed",
            },
            {
                "id": "http-response",
                "from": "api",
                "to": "browser",
                "y": 435,
                "label": "200 OK (JSON payload)",
                "variant": "return",
            },
        ],
        "activations": [
            {"participant": "browser", "from": 160, "to": 445, "type": "external"},
            {"participant": "api", "from": 165, "to": 440, "type": "backend"},
            {"participant": "redis", "from": 195, "to": 240, "type": "database"},
            {"participant": "postgres", "from": 285, "to": 330, "type": "database"},
            {"participant": "redis", "from": 360, "to": 375, "type": "database"},
        ],
        "cards": [
            {
                "dot": "cyan",
                "title": "Client Request",
                "items": [
                    "Browser initiates HTTP GET to the API handler",
                    "Connection remains open waiting for synchronous response",
                    "API receives the request and begins data retrieval",
                ],
            },
            {
                "dot": "amber",
                "title": "Cache-Aside Miss",
                "items": [
                    "API queries Redis cache using the resource key",
                    "Redis reports a cache miss (nil response)",
                    "API falls back to querying the primary persistent store",
                ],
            },
            {
                "dot": "emerald",
                "title": "Database Query & Cache Fill",
                "items": [
                    "API queries PostgreSQL to fetch authoritative data",
                    "PostgreSQL returns the matching row data",
                    "API populates Redis cache asynchronously with TTL for future hits",
                    "API sends HTTP 200 OK with JSON payload back to the browser",
                ],
            },
        ],
    }


def generate_diagram(
    repo_path: Path,
    name: str = "web-request-cache-miss",
    title: str | None = None,
    diagram_type: str = "sequence",
    quality: str = "showcase",
) -> dict[str, Any]:
    """Generate and finalize an interactive architecture diagram via Archify."""
    cmd_prefix, _ = find_archify_command()
    if not cmd_prefix:
        raise RuntimeError(
            f"Archify CLI is not installed or available. Install via 'npx skills add tt-a1i/archify -g'. Reference: {ARCHIFY_REPO}"
        )

    clean_name = name.strip().lower().replace(" ", "-")
    target_dir = repo_path / ".archify" / clean_name
    target_dir.mkdir(parents=True, exist_ok=True)

    candidate_file = target_dir / "candidate.json"
    output_html = target_dir / f"{clean_name}.html"
    rel_html = str(output_html.relative_to(repo_path))

    spec_title = title or clean_name.replace("-", " ").title()
    spec = build_cache_aside_spec(rel_html, spec_title)
    candidate_file.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    # Run Archify finalize
    cmd = [
        *cmd_prefix,
        "finalize",
        diagram_type,
        str(candidate_file.resolve()),
        str(output_html.resolve()),
        "--quality",
        quality,
        "--json",
    ]
    res = subprocess.run(
        cmd,
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=False,
    )

    if res.returncode != 0:
        # Fallback to render if finalize encounters validation edge case
        fallback_cmd = [
            *cmd_prefix,
            "render",
            diagram_type,
            str(candidate_file.resolve()),
            str(output_html.resolve()),
            "--quality",
            quality,
        ]
        res = subprocess.run(
            fallback_cmd,
            cwd=repo_path,
            text=True,
            capture_output=True,
            check=False,
        )

    if not output_html.exists():
        raise RuntimeError(
            f"Archify failed to produce HTML output: {res.stderr or res.stdout}"
        )

    return {
        "ok": True,
        "name": clean_name,
        "title": spec_title,
        "output_html": str(output_html.resolve()),
        "relative_html": rel_html,
        "size_bytes": output_html.stat().st_size,
        "repo": ARCHIFY_REPO,
    }

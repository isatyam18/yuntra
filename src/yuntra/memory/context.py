from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..service import ProjectService

SENSITIVE_NAMES = {".env", ".env.local", "id_rsa", "id_ed25519"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".html",
    ".css",
}


def estimate_tokens(text: str) -> int:
    """A reproducible character-based estimate; it is never provider token usage."""
    return max(1, (len(text) + 3) // 4) if text else 0


def query_terms(query: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9_/-]{3,}", query)}


def markdown_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^#{1,6}\s+(.+)$", text))
    if not matches:
        return [("document", text)]
    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        sections.append(("preamble", text[: matches[0].start()]))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((match.group(1).strip(), text[match.start() : end]))
    return sections


@dataclass(frozen=True)
class Candidate:
    path: str
    section: str
    content: str
    kind: str
    score: int


def _kind(path: Path) -> str:
    if path.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".html", ".css"}:
        return "code_and_tests"
    return "documentation"


def _excluded(path: Path, repository: Path, excluded_dirs: set[str]) -> bool:
    if (
        path.name.lower() in SENSITIVE_NAMES
        or path.name.lower().startswith(".env")
        or path.suffix.lower() in SENSITIVE_SUFFIXES
    ):
        return True
    try:
        return any(
            part in excluded_dirs for part in path.relative_to(repository).parts[:-1]
        )
    except ValueError:
        return True


def repository_candidates(
    repository: Path, excluded_dirs: Iterable[str], terms: set[str]
) -> tuple[list[Candidate], list[str]]:
    candidates: list[Candidate] = []
    omitted: list[str] = []
    excluded = set(excluded_dirs)
    for path in sorted(repository.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(repository).as_posix()
        if _excluded(path, repository, excluded):
            omitted.append(f"{relative}: excluded by security/profile rule")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            omitted.append(f"{relative}: unreadable text")
            continue
        if len(content) > 200_000:
            omitted.append(f"{relative}: exceeds 200KB retrieval limit")
            continue
        haystack = f"{relative}\n{content}".lower()
        score = sum(1 for term in terms if term in haystack)
        if terms and score == 0:
            continue
        sections = (
            markdown_sections(content)
            if path.suffix.lower() in {".md", ".rst"}
            else [("file", content)]
        )
        for section, body in sections:
            section_score = score + sum(1 for term in terms if term in section.lower())
            candidates.append(
                Candidate(relative, section, body, _kind(path), section_score)
            )
    return candidates, omitted


def build_context(project_data: Path, query: str = "") -> dict:
    """Return a deterministic context manifest and rendered compact context."""
    service = ProjectService(project_data.parent.parent)
    store = service.store(project_data)
    profile = store.profile(service._project_id(project_data))
    terms = query_terms(query)
    spec = (project_data / "PROJECT_SPEC.md").read_text(encoding="utf-8")
    spec_candidates = [
        Candidate(
            "PROJECT_SPEC.md",
            title,
            body,
            "project_instructions",
            1000 + sum(1 for term in terms if term in body.lower()),
        )
        for title, body in markdown_sections(spec)
    ]
    candidates, omitted = repository_candidates(
        Path(profile.repository_path), profile.context_exclusions, terms
    )
    candidates.extend(spec_candidates)
    try:
        checkpoint, _ = service.resume(project_data)
        state_text = f"Lifecycle: {checkpoint.lifecycle_state}\nNext action: {checkpoint.next_action}\nBlockers: {', '.join(checkpoint.blockers) or 'none'}\nPending tests: {', '.join(checkpoint.pending_tests) or 'none'}"
        candidates.append(
            Candidate("checkpoint", "working state", state_text, "working_state", 900)
        )
    except ValueError:
        pass
    decisions = store.decisions(profile.project_id)
    if decisions:
        decision_text = "\n".join(
            f"{d['decision_id']}: {d['chosen_approach']} — {d['rationale']}"
            for d in decisions
        )
        candidates.append(
            Candidate(
                "decisions",
                "decision history",
                decision_text,
                "historical_decisions",
                500,
            )
        )
    selected: list[dict] = []
    seen_hashes: set[str] = set()
    used = {key: 0 for key in profile.context_budgets}
    duplicates = 0
    for candidate in sorted(
        candidates, key=lambda item: (-item.score, item.path, item.section)
    ):
        digest = hashlib.sha256(candidate.content.strip().encode("utf-8")).hexdigest()
        if digest in seen_hashes:
            duplicates += 1
            continue
        seen_hashes.add(digest)
        budget = profile.context_budgets[candidate.kind]
        tokens = estimate_tokens(candidate.content)
        available = budget - used[candidate.kind]
        if available <= 0:
            omitted.append(
                f"{candidate.path}#{candidate.section}: {candidate.kind} budget exhausted"
            )
            continue
        content = candidate.content
        truncated = False
        if tokens > available:
            content = content[: available * 4]
            tokens = estimate_tokens(content)
            truncated = True
        used[candidate.kind] += tokens
        selected.append(
            {
                "path": candidate.path,
                "section": candidate.section,
                "kind": candidate.kind,
                "score": candidate.score,
                "estimated_tokens": tokens,
                "truncated": truncated,
                "content": content,
            }
        )
    rendered = "\n\n".join(
        f"## {item['path']} — {item['section']}\n{item['content']}" for item in selected
    )
    manifest = {
        "query": query,
        "token_estimate": True,
        "budgets": profile.context_budgets,
        "used": used,
        "files_or_sections": len(selected),
        "duplicate_content_removed": duplicates,
        "omitted": omitted,
        "retrieval_provenance": "deterministic local metadata and keyword matching",
        "items": [
            {key: value for key, value in item.items() if key != "content"}
            for item in selected
        ],
    }
    return {"manifest": manifest, "context": rendered}


def benchmark_context(project_data: Path, query: str = "") -> dict:
    """Compare selected context to a reproducible local all-text baseline."""
    service = ProjectService(project_data.parent.parent)
    store = service.store(project_data)
    profile = store.profile(service._project_id(project_data))
    candidates, exclusions = repository_candidates(
        Path(profile.repository_path), profile.context_exclusions, set()
    )
    spec = (project_data / "PROJECT_SPEC.md").read_text(encoding="utf-8")
    baseline_text = spec + "\n" + "\n".join(item.content for item in candidates)
    selected = build_context(project_data, query)
    baseline = estimate_tokens(baseline_text)
    selected_tokens = estimate_tokens(selected["context"])
    return {
        "methodology": "Baseline is every eligible local text file plus PROJECT_SPEC.md; selection uses identical repository state with deterministic keyword ranking and configured budgets.",
        "token_estimate": True,
        "baseline_estimated_tokens": baseline,
        "selected_estimated_tokens": selected_tokens,
        "estimated_reduction_tokens": max(0, baseline - selected_tokens),
        "estimated_reduction_percent": round(
            (max(0, baseline - selected_tokens) / baseline * 100), 2
        )
        if baseline
        else 0,
        "excluded_items": exclusions,
        "manifest": selected["manifest"],
    }

from __future__ import annotations

from ..models import ProjectProfile


class PolicyViolation(PermissionError):
    pass


POLICY_KEYS = {
    "auto_commit": "allow_auto_commit",
    "git_push": "allow_git_push",
    "dependency_install": "allow_dependency_install",
    "network": "allow_network",
    "destructive_operation": "allow_destructive_operations",
}


def require_policy(profile: ProjectProfile, operation: str) -> None:
    key = POLICY_KEYS.get(operation)
    if key is None:
        raise PolicyViolation(f"Unknown high-risk operation: {operation}")
    if not profile.policies.get(key, False):
        raise PolicyViolation(
            f"Policy blocks {operation}; enable {key} only with explicit user approval."
        )

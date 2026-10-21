from .models import LifecycleState

_TRANSITIONS = {
    LifecycleState.NEW: {LifecycleState.PLANNING, LifecycleState.CANCELLED},
    LifecycleState.PLANNING: {
        LifecycleState.REVIEW,
        LifecycleState.PAUSED,
        LifecycleState.CANCELLED,
    },
    LifecycleState.REVIEW: {
        LifecycleState.PLANNING,
        LifecycleState.APPROVED,
        LifecycleState.BLOCKED,
        LifecycleState.CANCELLED,
    },
    LifecycleState.APPROVED: {
        LifecycleState.REVIEW,
        LifecycleState.EXECUTING,
        LifecycleState.VERIFYING,
        LifecycleState.PAUSED,
        LifecycleState.CANCELLED,
    },
    LifecycleState.EXECUTING: {
        LifecycleState.REVIEW,
        LifecycleState.VERIFYING,
        LifecycleState.PAUSED,
        LifecycleState.BLOCKED,
        LifecycleState.FAILED,
    },
    LifecycleState.VERIFYING: {
        LifecycleState.COMPLETED,
        LifecycleState.EXECUTING,
        LifecycleState.FAILED,
        LifecycleState.BLOCKED,
    },
    LifecycleState.PAUSED: {
        LifecycleState.PLANNING,
        LifecycleState.REVIEW,
        LifecycleState.APPROVED,
        LifecycleState.EXECUTING,
        LifecycleState.VERIFYING,
        LifecycleState.CANCELLED,
    },
    LifecycleState.BLOCKED: {
        LifecycleState.PLANNING,
        LifecycleState.REVIEW,
        LifecycleState.EXECUTING,
        LifecycleState.VERIFYING,
        LifecycleState.FAILED,
        LifecycleState.CANCELLED,
    },
    LifecycleState.FAILED: {
        LifecycleState.PLANNING,
        LifecycleState.REVIEW,
        LifecycleState.EXECUTING,
        LifecycleState.CANCELLED,
    },
    LifecycleState.COMPLETED: set(),
    LifecycleState.CANCELLED: set(),
}


def can_transition(current: LifecycleState, target: LifecycleState) -> bool:
    return target in _TRANSITIONS[current]

from .manual import ManualCliAdapter


class ClaudeCodeAdapter(ManualCliAdapter):
    name = "claude-code"
    executable_name = "claude"
    display_name = "Claude Code"

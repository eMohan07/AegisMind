from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

AUTO_TOOLS = frozenset({"search_local_knowledge", "read_system_file"})
APPROVAL_TOOLS = frozenset({"create_note", "run_local_command", "save_memory"})

DENY_PATH_PATTERNS: tuple[str, ...] = ()
ALLOWED_COMMAND_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("git", "status"),
    ("git", "log"),
    ("docker", "ps"),
    ("docker", "logs"),
    ("tail",),
    ("Get-Content",),
    ("powershell", "Get-Content"),
    ("powershell.exe", "Get-Content"),
)


def evaluate(tool_name: str, args: dict[str, Any]) -> str:
    """Evaluate the policy for a tool call and return 'auto', 'approval', or 'deny'.

    auto: search_local_knowledge, read_system_file.
    approval: create_note, run_local_command, save_memory.
    deny: denylisted paths, commands not on the allowlist.
    """
    if tool_name in AUTO_TOOLS:
        return "auto"

    if tool_name in APPROVAL_TOOLS:
        if tool_name == "run_local_command":
            cmd = str(args.get("cmd", ""))
            if not _is_command_allowlisted(cmd):
                return "deny"
        if tool_name == "create_note":
            path = str(args.get("path", "")) if "path" in args else ""
            if path and _is_denied_path(path):
                return "deny"
        return "approval"

    if tool_name == "save_memory":
        return "approval"

    return "deny"


def _is_command_allowlisted(cmd: str) -> bool:
    import shlex
    import sys

    try:
        argv = shlex.split(cmd.strip(), posix=(sys.platform != "win32"))
    except Exception:
        return False
    if not argv:
        return False
    clean_argv = [a.lower().strip() for a in argv]
    for prefix in ALLOWED_COMMAND_PREFIXES:
        prefix_lower = [p.lower().strip() for p in prefix]
        if len(clean_argv) >= len(prefix_lower) and clean_argv[: len(prefix_lower)] == prefix_lower:
            return True
    return False


def _is_denied_path(path: str) -> bool:
    clean = path.strip().strip("'\"")
    if ".." in clean.replace("\\", "/").split("/"):
        return True
    return False


def compute_risk(
    tool_name: str, is_new: bool = True, tainted: bool = False
) -> str:
    """Compute risk level based on tool, action type, and taint.

    new note = low, overwrite note = medium,
    run_local_command = medium, save_memory = low,
    tainted = one level higher.
    """
    if tool_name == "save_memory":
        risk = "low"
    elif tool_name == "create_note":
        risk = "low" if is_new else "medium"
    elif tool_name == "run_local_command":
        risk = "medium"
    else:
        risk = "low"

    if tainted:
        if risk == "low":
            risk = "medium"
        elif risk == "medium":
            risk = "high"

    return risk

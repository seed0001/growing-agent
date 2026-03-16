"""
Tool absorber.

Moves a tested draft into the live dynamic tool directory.
The dynamic loader picks it up immediately on the next tool dispatch.

Flow: draft passes test → absorb_tool → live in src/tools/dynamic/
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

from config.settings import (
    DYNAMIC_TOOLS_DIR,
    TOOLS_DRAFTS_DIR,
    TOOLS_REJECTED_DIR,
    TOOLS_TESTS_DIR,
)


def _last_test(name: str) -> dict | None:
    path = TOOLS_TESTS_DIR / f"{name}_latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def absorb_tool(name: str, force: bool = False) -> str:
    """
    Absorb a tested draft into the live toolset.

    Requires the last test to have passed unless force=True.
    Copies the draft to src/tools/dynamic/{name}.py.
    The dynamic loader will pick it up on the next call.
    """
    name = name.strip()
    draft = TOOLS_DRAFTS_DIR / f"{name}.py"
    if not draft.exists():
        return f"Error: draft '{name}' not found. Write it with write_tool_draft first."

    if not force:
        test = _last_test(name)
        if test is None:
            return f"Error: no test results for '{name}'. Run test_tool first."
        if not test.get("ok"):
            return (
                f"Error: last test FAILED for '{name}'. "
                f"Fix the draft and re-test before absorbing. "
                f"Error was: {test.get('error', 'unknown')}"
            )

    dest = DYNAMIC_TOOLS_DIR / f"{name}.py"
    DYNAMIC_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(draft), str(dest))

    # Write absorption log
    log = {
        "name": name,
        "absorbed_at": datetime.now().isoformat(timespec="seconds"),
        "forced": force,
        "source": str(draft),
        "dest": str(dest),
    }
    log_path = DYNAMIC_TOOLS_DIR / f"{name}.absorbed.json"
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

    return (
        f"Tool '{name}' absorbed and is now live.\n"
        f"Location: {dest}\n"
        f"It will be available on the next tool dispatch."
    )


def reject_tool(name: str, reason: str = "") -> str:
    """
    Move a draft to the rejected archive with an optional reason.
    Use this when a draft fails tests and should not be retried as-is.
    """
    name = name.strip()
    draft = TOOLS_DRAFTS_DIR / f"{name}.py"
    if not draft.exists():
        return f"Draft '{name}' not found."
    TOOLS_REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = TOOLS_REJECTED_DIR / f"{name}_{ts}.py"
    shutil.move(str(draft), str(dest))
    if reason:
        note_path = TOOLS_REJECTED_DIR / f"{name}_{ts}.reason.txt"
        note_path.write_text(f"Rejected: {datetime.now().isoformat()}\nReason: {reason}\n", encoding="utf-8")
    return f"Draft '{name}' rejected and archived." + (f" Reason: {reason}" if reason else "")


def list_absorbed_tools() -> str:
    """List all absorbed (live) tools."""
    tools = [
        p for p in DYNAMIC_TOOLS_DIR.glob("*.py")
        if not p.name.startswith("_")
    ]
    if not tools:
        return "No tools absorbed yet. Build one with write_tool_draft → test_tool → absorb_tool."
    lines = []
    for t in sorted(tools):
        # Try to read the TOOL_META description
        desc = ""
        try:
            code = t.read_text(encoding="utf-8")
            for line in code.split("\n"):
                if '"description"' in line and ":" in line:
                    desc = line.split(":", 1)[-1].strip().strip('",')
                    break
        except Exception:
            pass
        lines.append(f"- {t.stem}" + (f"  — {desc}" if desc else ""))
    return f"Live tools ({len(tools)}):\n" + "\n".join(lines)

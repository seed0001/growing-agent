"""
Evolution log — JSONL, append-only.

Every word the agent generates, every tool it calls, every result it got back.
One JSON object per line. Read it in any text editor or stream it with `tail -f`.

File: logs/evolution.jsonl
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from config.settings import LOGS_DIR

LOG_PATH = LOGS_DIR / "evolution.jsonl"

_cycle_counter = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _write(event: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def log_cycle_start() -> int:
    global _cycle_counter
    _cycle_counter += 1
    _write({"ts": _now(), "type": "cycle_start", "cycle": _cycle_counter})
    return _cycle_counter


def log_model_output(cycle: int, content: str) -> None:
    if not (content or "").strip():
        return
    _write({"ts": _now(), "type": "model_output", "cycle": cycle, "content": content})


def log_tool_call(cycle: int, name: str, args: dict) -> None:
    # Truncate large args (e.g. full code blocks) to keep the log readable
    safe_args = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 800:
            safe_args[k] = v[:800] + f"... [{len(v)} chars total]"
        else:
            safe_args[k] = v
    _write({"ts": _now(), "type": "tool_call", "cycle": cycle, "tool": name, "args": safe_args})


def log_tool_result(cycle: int, name: str, result: str) -> None:
    r = (result or "")
    _write({
        "ts": _now(), "type": "tool_result", "cycle": cycle,
        "tool": name,
        "result": r[:2000] + (f"... [{len(r)} chars total]" if len(r) > 2000 else ""),
    })


def log_cycle_end(cycle: int, summary: str = "") -> None:
    _write({"ts": _now(), "type": "cycle_end", "cycle": cycle, "summary": (summary or "")[:500]})


def log_kill(cycle: int) -> None:
    _write({"ts": _now(), "type": "killed", "cycle": cycle})


def log_error(cycle: int, error: str) -> None:
    _write({"ts": _now(), "type": "error", "cycle": cycle, "error": str(error)[:1000]})


def log_panel_update(cycle: int, panel: str, content: str) -> None:
    """Called every time the agent pushes content to a UI panel."""
    if not (content or "").strip():
        return
    _write({
        "ts": _now(), "type": "panel_update", "cycle": cycle,
        "panel": panel,
        "content": (content or "")[:600],
    })


def log_reset() -> None:
    _write({"ts": _now(), "type": "reset", "note": "All state wiped. Starting from zero."})


def get_recent_lines(n: int = 100) -> list[dict]:
    """Return the last n log entries as parsed dicts."""
    if not LOG_PATH.exists():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        recent = lines[-n:]
        result = []
        for line in recent:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                result.append({"raw": line})
        return result
    except OSError:
        return []

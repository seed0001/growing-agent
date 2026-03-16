"""
Tool draft editor.

The agent writes tool code here before testing and absorbing.
Drafts live in data/tools/drafts/ and are not live until absorbed.

A valid draft must expose a TOOL_META dict and at least one async function.
"""
from datetime import datetime
from pathlib import Path

from config.settings import TOOLS_DRAFTS_DIR

_TEMPLATE = '''"""
{description}
Auto-drafted by agent on {timestamp}.
"""

TOOL_META = {{
    "name": "{name}",
    "description": "{description}",
    "parameters": {{
        "type": "object",
        "properties": {{
            # Define your parameters here
            # "param_name": {{"type": "string", "description": "..."}}
        }},
        "required": [],
    }},
}}


async def {name}(**kwargs) -> str:
    """
    {description}
    """
    # Your implementation here
    return "Not yet implemented."
'''


def write_tool_draft(name: str, code: str, description: str = "") -> str:
    """Write or overwrite a tool draft. name = function/file name (no .py)."""
    name = name.strip().replace(" ", "_").replace("-", "_")
    if not name:
        return "Error: name required."
    code = code.strip()
    if not code:
        return "Error: code required."
    TOOLS_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TOOLS_DRAFTS_DIR / f"{name}.py"
    path.write_text(code, encoding="utf-8")
    return f"Draft saved: '{name}.py' ({len(code)} chars)"


def get_draft_template(name: str, description: str = "") -> str:
    """Return a starter template for a new tool draft."""
    name = name.strip().replace(" ", "_").replace("-", "_") or "my_tool"
    desc = description.strip() or f"A tool named {name}."
    return _TEMPLATE.format(
        name=name,
        description=desc,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )


def read_tool_draft(name: str) -> str:
    """Read back a draft by name."""
    name = name.strip()
    path = TOOLS_DRAFTS_DIR / f"{name}.py"
    if not path.exists():
        path = TOOLS_DRAFTS_DIR / (name if name.endswith(".py") else f"{name}.py")
    if not path.exists():
        available = [p.stem for p in TOOLS_DRAFTS_DIR.glob("*.py")]
        return f"Draft '{name}' not found. Available: {', '.join(available) or 'none'}"
    return path.read_text(encoding="utf-8", errors="replace")


def list_tool_drafts() -> str:
    """List all pending drafts."""
    drafts = sorted(TOOLS_DRAFTS_DIR.glob("*.py"))
    if not drafts:
        return "No drafts. Use write_tool_draft to create one."
    lines = []
    for p in drafts:
        size = p.stat().st_size
        mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        lines.append(f"- {p.stem}  ({size} bytes, modified {mtime})")
    return f"Drafts ({len(drafts)}):\n" + "\n".join(lines)


def delete_tool_draft(name: str) -> str:
    """Delete a draft."""
    path = TOOLS_DRAFTS_DIR / f"{name}.py"
    if path.exists():
        path.unlink()
        return f"Draft '{name}' deleted."
    return f"Draft '{name}' not found."

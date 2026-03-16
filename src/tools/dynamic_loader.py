"""
Dynamic tool loader.

Scans src/tools/dynamic/ for .py files that expose TOOL_META and
an async function. Returns (tool_definitions, runners) for use in the
agent's tool dispatch.

Hot-reloads on every call — after absorb_tool, the new tool is
immediately available without restarting the agent.
"""
import importlib.util
import inspect
from pathlib import Path

from config.settings import DYNAMIC_TOOLS_DIR


def load_dynamic_tools() -> tuple[list[dict], dict]:
    """
    Returns:
        tool_definitions: list of OpenAI-format function schemas
        runners: dict mapping tool name → async callable
    """
    definitions = []
    runners = {}

    if not DYNAMIC_TOOLS_DIR.exists():
        return definitions, runners

    for path in sorted(DYNAMIC_TOOLS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"dynamic.{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            meta = getattr(mod, "TOOL_META", None)
            if not meta or not isinstance(meta, dict):
                continue

            name = meta.get("name", path.stem)
            description = meta.get("description", "")
            parameters = meta.get("parameters", {"type": "object", "properties": {}})

            definitions.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            })

            # Find the matching async function
            fn = getattr(mod, name, None)
            if fn is None:
                # Fall back to first async function
                for fname, obj in inspect.getmembers(mod, inspect.iscoroutinefunction):
                    fn = obj
                    break

            if fn:
                runners[name] = fn

        except Exception:
            continue

    return definitions, runners

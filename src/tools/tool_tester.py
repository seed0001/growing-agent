"""
Subprocess-isolated tool tester.

Runs a draft tool in a fresh Python subprocess so a crash, syntax error,
or infinite loop cannot take down the agent. Results are stored in
data/tools/tests/<name>_latest.json.
"""
import asyncio
import json
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from config.settings import TOOLS_DRAFTS_DIR, TOOLS_TESTS_DIR

TIMEOUT_SEC = 30


def _test_script(draft_path: str, tool_name: str, call_args: dict) -> str:
    """Generate the harness script that runs inside the subprocess."""
    args_repr = json.dumps(call_args)
    return textwrap.dedent(f"""
import asyncio, json, sys, importlib.util, traceback
spec = importlib.util.spec_from_file_location("draft", r"{draft_path}")
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except Exception as e:
    print(json.dumps({{"ok": False, "error": f"Import error: {{e}}", "traceback": traceback.format_exc()}}))
    sys.exit(1)

fn = getattr(mod, "{tool_name}", None)
if fn is None:
    # Try to find any async function
    import inspect
    fns = [n for n, f in inspect.getmembers(mod, inspect.iscoroutinefunction)]
    if fns:
        fn = getattr(mod, fns[0])
    else:
        print(json.dumps({{"ok": False, "error": f"No function '{tool_name}' found in draft."}}))
        sys.exit(1)

args = {args_repr}
try:
    result = asyncio.run(fn(**args))
    print(json.dumps({{"ok": True, "result": str(result)}}))
except Exception as e:
    print(json.dumps({{"ok": False, "error": str(e), "traceback": traceback.format_exc()}}))
""").strip()


async def test_tool(name: str, test_args: dict | None = None) -> str:
    """
    Run a draft tool in isolation. Returns a human-readable test report.
    test_args: dict of keyword arguments to pass to the tool function.
    Results saved to data/tools/tests/<name>_latest.json.
    """
    name = name.strip()
    draft_path = TOOLS_DRAFTS_DIR / f"{name}.py"
    if not draft_path.exists():
        return f"Error: draft '{name}' not found. Use list_tool_drafts to see what exists."

    call_args = test_args or {}
    harness = _test_script(str(draft_path), name, call_args)

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", harness,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SEC)
    except asyncio.TimeoutError:
        result = {"ok": False, "error": f"Timed out after {TIMEOUT_SEC}s", "traceback": ""}
    except Exception as e:
        result = {"ok": False, "error": str(e), "traceback": ""}
    else:
        raw = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            result = {"ok": False, "error": "Could not parse subprocess output", "raw": raw, "stderr": err}
        if err and not result.get("ok"):
            result["stderr"] = err

    # Save result
    TOOLS_TESTS_DIR.mkdir(parents=True, exist_ok=True)
    result["tool_name"] = name
    result["tested_at"] = datetime.now().isoformat(timespec="seconds")
    result["test_args"] = call_args
    test_path = TOOLS_TESTS_DIR / f"{name}_latest.json"
    test_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if result.get("ok"):
        return (
            f"TEST PASSED: '{name}'\n"
            f"Result: {result.get('result', '')}\n"
            f"Tested at: {result['tested_at']}"
        )
    else:
        tb = result.get("traceback", "").strip()
        err_msg = result.get("error", "unknown error")
        return (
            f"TEST FAILED: '{name}'\n"
            f"Error: {err_msg}\n"
            + (f"Traceback:\n{tb}" if tb else "")
        )


def get_test_result(name: str) -> str:
    """Read the latest test result for a draft."""
    path = TOOLS_TESTS_DIR / f"{name}_latest.json"
    if not path.exists():
        return f"No test results found for '{name}'. Run test_tool first."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        status = "PASSED" if data.get("ok") else "FAILED"
        lines = [
            f"Test result for '{name}': {status}",
            f"Tested at: {data.get('tested_at', '?')}",
            f"Args: {data.get('test_args', {})}",
        ]
        if data.get("ok"):
            lines.append(f"Result: {data.get('result', '')}")
        else:
            lines.append(f"Error: {data.get('error', '')}")
            if data.get("traceback"):
                lines.append(f"Traceback: {data['traceback'][:500]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading test result: {e}"

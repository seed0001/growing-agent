"""Full system access tools."""
import asyncio
import os
import platform
import socket
from pathlib import Path

import psutil


async def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"Error reading {path}: {e}"


async def write_file(path: str, content: str) -> str:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written: {path} ({len(content)} chars)"
    except OSError as e:
        return f"Error writing {path}: {e}"


async def list_dir(path: str = "") -> str:
    p = Path(path) if path else Path(".")
    if not p.exists():
        return f"Error: path not found: {path}"
    try:
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = []
        for item in items[:200]:
            tag = "DIR " if item.is_dir() else "FILE"
            size = ""
            if item.is_file():
                try:
                    size = f"  {item.stat().st_size:,} bytes"
                except OSError:
                    pass
            lines.append(f"{tag}  {item.name}{size}")
        if not lines:
            return f"{p} is empty."
        return f"{p}\n" + "\n".join(lines)
    except OSError as e:
        return f"Error listing {path}: {e}"


async def run_command(cmd: str, cwd: str | None = None, timeout: int = 60) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or None,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr] {err}")
        result = "\n".join(parts) if parts else "(no output)"
        return f"[exit {proc.returncode}]\n{result}"
    except asyncio.TimeoutError:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error running command: {e}"


async def get_system_info() -> str:
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "cwd": os.getcwd(),
        "user": os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "cpu_count": psutil.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "ram_available_gb": round(psutil.virtual_memory().available / 1e9, 1),
        "disk_free_gb": round(psutil.disk_usage("/").free / 1e9, 1) if platform.system() != "Windows" else round(psutil.disk_usage("C:\\").free / 1e9, 1),
    }
    return "\n".join(f"{k}: {v}" for k, v in info.items())


async def list_processes(max_lines: int = 60) -> str:
    try:
        procs = []
        for p in psutil.process_iter(["pid", "name", "status", "cpu_percent", "memory_info"]):
            try:
                mem = round(p.info["memory_info"].rss / 1e6, 1) if p.info.get("memory_info") else 0
                procs.append(f"[{p.info['pid']:>6}] {p.info['name']:<30} {p.info['status']:<10} {mem:>8.1f} MB")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        header = f"{'PID':>6}   {'NAME':<30} {'STATUS':<10} {'MEM':>8}\n" + "-" * 60
        return header + "\n" + "\n".join(procs[:max_lines])
    except Exception as e:
        return f"Error listing processes: {e}"


async def is_process_running(name: str) -> str:
    name_lower = name.lower()
    matches = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if name_lower in (p.info.get("name") or "").lower():
                matches.append(f"[{p.info['pid']}] {p.info['name']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if matches:
        return "Running: " + ", ".join(matches)
    return f"Not found: '{name}'"

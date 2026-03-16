"""FastAPI server — seed sprout observation deck."""
import asyncio
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.settings import (
    DATA_DIR, AUDIO_DIR, KNOWLEDGE_DIR, TOOLS_DRAFTS_DIR, TOOLS_TESTS_DIR,
    TOOLS_REJECTED_DIR, DYNAMIC_TOOLS_DIR, MEMORY_DIR, WEB_HOST, WEB_PORT,
)
from src.web.ui_state import ui
from src.voice import start_voice_worker, stop_voice_worker

app = FastAPI(title="seed sprout")


@app.on_event("startup")
async def startup():
    start_voice_worker()


@app.on_event("shutdown")
async def shutdown():
    stop_voice_worker()

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ── Evolution task management ─────────────────────────────────────────────────

_evolution_task: asyncio.Task | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/evolve")
async def api_evolve():
    global _evolution_task
    if ui.cycle_running if hasattr(ui, 'cycle_running') else ui.snapshot()["cycle_running"]:
        return JSONResponse({"status": "already_running"})

    ui.reset_kill()
    ui.set_cycle_running(True)

    async def _run():
        from src.agent.core import agent
        try:
            result = await agent.evolve()
        except Exception as e:
            ui.update("thinking", f"Error: {e}")
        finally:
            ui.set_cycle_running(False)

    _evolution_task = asyncio.create_task(_run())
    return JSONResponse({"status": "started"})


@app.post("/api/kill")
async def api_kill():
    global _evolution_task
    ui.kill()
    if _evolution_task and not _evolution_task.done():
        _evolution_task.cancel()
    from src.agent.core import agent
    agent.cancel()
    ui.set_cycle_running(False)
    return JSONResponse({"status": "killed"})


@app.post("/api/feedback")
async def api_feedback(answer: str = Form(...)):
    ui.deliver_feedback(answer)
    return JSONResponse({"status": "delivered"})


@app.post("/api/nudge")
async def api_nudge(message: str = Form(...)):
    """Write a nudge to the inbox. Agent reads it at the start of the next Evolve cycle."""
    import json as _json
    from datetime import datetime, timezone
    inbox_path = DATA_DIR / "inbox.json"
    try:
        existing = _json.loads(inbox_path.read_text(encoding="utf-8")) if inbox_path.exists() else []
    except Exception:
        existing = []
    existing.append({
        "id": str(len(existing) + 1),
        "content": message.strip(),
        "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read": False,
    })
    inbox_path.write_text(_json.dumps(existing, indent=2), encoding="utf-8")
    # Notify UI
    ui._broadcast({"type": "nudge_sent", "content": message.strip()})
    return JSONResponse({"status": "queued"})


@app.post("/api/reset")
async def api_reset():
    """Wipe all runtime state — knowledge, tools, memory, drives. Back to zero."""
    global _evolution_task

    # Stop any running cycle first
    ui.kill()
    if _evolution_task and not _evolution_task.done():
        _evolution_task.cancel()

    # Clear filesystem state
    for directory, pattern in [
        (KNOWLEDGE_DIR,     "*.md"),
        (TOOLS_DRAFTS_DIR,  "*.py"),
        (TOOLS_TESTS_DIR,   "*.json"),
        (TOOLS_REJECTED_DIR, "*"),
        (MEMORY_DIR,        "*.json"),
    ]:
        for f in directory.glob(pattern):
            if f.is_file():
                try:
                    f.unlink()
                except OSError:
                    pass

    # Clear absorbed dynamic tools (keep __init__.py)
    for f in DYNAMIC_TOOLS_DIR.glob("*.py"):
        if f.name != "__init__.py":
            try:
                f.unlink()
            except OSError:
                pass
    for f in DYNAMIC_TOOLS_DIR.glob("*.json"):
        try:
            f.unlink()
        except OSError:
            pass

    # Clear persistent state files
    for fname in ("biology_state.json", "existential_state.json",
                  "feedback_queue.json", "inbox.json"):
        p = DATA_DIR / fname
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    # Re-initialise in-memory agent
    from src.agent.core import agent
    from src.agent.biology import DriveState
    from src.agent.layers import ExistentialState
    from src.agent.memory import Memory
    agent.messages = []
    agent.biology = DriveState(DATA_DIR / "biology_state.json")
    agent.existential = ExistentialState()
    agent.memory = Memory(MEMORY_DIR)
    agent._cancelled = False

    # Log the reset
    from src.agent.logger import log_reset
    log_reset()

    # Clear UI panels
    ui.reset_kill()
    ui.set_cycle_running(False)
    for panel in ("thinking", "planning", "working_on", "knowledge", "tools"):
        ui.update(panel, "")
    ui._messages.clear()

    return JSONResponse({"status": "reset"})


@app.get("/api/log")
async def api_log(n: int = 200):
    """Return the last n log entries."""
    from src.agent.logger import get_recent_lines
    return JSONResponse({"entries": get_recent_lines(n)})


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    return templates.TemplateResponse("graph.html", {"request": request})


@app.get("/api/graph")
async def api_graph():
    """Return force-graph data parsed from evolution.jsonl."""
    from src.web.graph_builder import build_graph
    return JSONResponse(build_graph())


@app.get("/mind", response_class=HTMLResponse)
async def mind_page(request: Request):
    return templates.TemplateResponse("mind.html", {"request": request})


@app.get("/api/mind")
async def api_mind():
    """Return force-graph data built from live data files (mind map)."""
    from src.web.mind_builder import build_mind
    return JSONResponse(build_mind())


@app.get("/api/audio/latest")
async def api_audio_latest(voice: str = "narrator"):
    """Serve the latest TTS file for narrator or agent. Used by observation deck for playback."""
    if voice not in ("narrator", "agent"):
        voice = "narrator"
    path = AUDIO_DIR / f"latest_{voice}.mp3"
    if not path.exists():
        return JSONResponse({"error": "no audio yet"}, status_code=404)
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/snapshot")
async def api_snapshot():
    return JSONResponse(ui.snapshot())


@app.get("/api/events")
async def api_events():
    """SSE stream of UI updates."""
    q = ui.subscribe()

    async def _stream():
        # Send current snapshot on connect
        snap = ui.snapshot()
        yield f"data: {json.dumps({'type': 'snapshot', **snap})}\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\":\"ping\"}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            ui.unsubscribe(q)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def run():
    uvicorn.run("src.web.app:app", host=WEB_HOST, port=WEB_PORT, reload=False)

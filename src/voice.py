"""
Shared TTS queue — documentary narrator and organism speak at different times.

One queue, two voices:
  - narrator: Discovery-style observer (Ryan)
  - agent: the organism's own voice when it chooses to speak

Neither speaks over the other; playback is driven by the observation deck UI.
"""
import asyncio
from pathlib import Path

from config.settings import AUDIO_DIR
from src.web.ui_state import ui

# Edge TTS voice IDs
VOICE_NARRATOR = "en-GB-RyanNeural"   # Documentary narrator
VOICE_AGENT    = "en-US-ChristopherNeural"  # Organism's own voice (distinct from Ryan)

_queue: asyncio.Queue[tuple[str, str]] | None = None
_worker_task: asyncio.Task | None = None


def _get_queue() -> asyncio.Queue[tuple[str, str]]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


def queue_speak(text: str, voice: str = "narrator") -> None:
    """Enqueue a line to be spoken. voice is 'narrator' or 'agent'. Non-blocking."""
    if not (text or "").strip():
        return
    voice_id = VOICE_NARRATOR if voice == "narrator" else VOICE_AGENT
    _get_queue().put_nowait((text.strip(), voice_id))


async def _tts_worker() -> None:
    """Run TTS for each queued (text, voice_id); save to AUDIO_DIR and broadcast tts_ready."""
    import edge_tts
    q = _get_queue()
    while True:
        try:
            text, voice_id = await q.get()
        except asyncio.CancelledError:
            break
        out_name = "narrator" if voice_id == VOICE_NARRATOR else "agent"
        out_path = AUDIO_DIR / f"latest_{out_name}.mp3"
        try:
            communicate = edge_tts.Communicate(text, voice_id)
            await communicate.save(str(out_path))
            ui._broadcast({
                "type": "tts_ready",
                "voice": out_name,
                "url": f"/api/audio/latest?voice={out_name}",
                "text": text[:200],
            })
        except Exception:
            pass
        q.task_done()


def start_voice_worker() -> None:
    """Start the TTS worker task. Call from app lifespan."""
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_tts_worker())


def stop_voice_worker() -> None:
    """Cancel the TTS worker."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        _worker_task = None

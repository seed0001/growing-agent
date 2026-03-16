"""
UI state manager.

Holds the live panel state and broadcasts updates to connected SSE clients.
Also manages the feedback queue (agent requests input from user).

Panels:
  thinking    — current thought / reasoning stream
  planning    — what the agent intends to do this cycle
  working_on  — the active tool call / action
  knowledge   — latest knowledge entry written
  tools       — list of absorbed tools
  messages    — messages the agent sent via send_message (built by agent)
  custom      — arbitrary panels the agent registers dynamically
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any


class UIState:
    def __init__(self):
        self._panels: dict[str, str] = {
            "thinking":   "",
            "planning":   "",
            "working_on": "",
            "knowledge":  "",
            "tools":      "",
        }
        self._messages: list[dict] = []          # agent → user messages
        self._custom_panels: dict[str, str] = {} # agent-registered panels
        self._subscribers: list[asyncio.Queue] = []
        self._feedback_event = asyncio.Event()
        self._feedback_question: str = ""
        self._feedback_answer: str = ""
        self._feedback_pending: bool = False
        self._kill_flag: bool = False
        self._cycle_running: bool = False

    # ── Panel updates ──────────────────────────────────────────────────────

    def update(self, panel: str, content: str) -> None:
        """Update a named panel and broadcast to all SSE subscribers."""
        if panel in self._panels:
            self._panels[panel] = content
        else:
            self._custom_panels[panel] = content
        self._broadcast({"type": "panel", "panel": panel, "content": content})

    def register_panel(self, name: str, initial_content: str = "") -> str:
        """Agent calls this to add a new panel to the UI."""
        if name in self._panels:
            return f"Panel '{name}' already exists."
        self._custom_panels[name] = initial_content
        self._broadcast({"type": "new_panel", "panel": name, "content": initial_content})
        return f"Panel '{name}' registered."

    def add_message(self, content: str) -> str:
        """Agent sends a message to the user via the messages panel."""
        msg = {"content": content, "sent_at": datetime.now(timezone.utc).isoformat()}
        self._messages.append(msg)
        self._broadcast({"type": "message", "content": content, "sent_at": msg["sent_at"]})
        return f"Message sent: {content[:80]}"

    # ── Feedback ───────────────────────────────────────────────────────────

    async def request_feedback(self, question: str, timeout_sec: float = 300.0) -> str:
        """
        Block until user responds or timeout. Returns the response or a
        timeout notice. Broadcasts a feedback_requested event.
        """
        self._feedback_question = question
        self._feedback_answer = ""
        self._feedback_pending = True
        self._feedback_event.clear()
        self._broadcast({"type": "feedback_requested", "question": question})

        try:
            await asyncio.wait_for(self._feedback_event.wait(), timeout=timeout_sec)
            answer = self._feedback_answer
        except asyncio.TimeoutError:
            answer = "[no response — user did not answer within timeout]"
        finally:
            self._feedback_pending = False
            self._broadcast({"type": "feedback_resolved", "answer": answer})

        return answer

    def deliver_feedback(self, answer: str) -> None:
        """Called by the web endpoint when the user submits a feedback response."""
        self._feedback_answer = answer
        self._feedback_event.set()

    # ── Kill / lifecycle ───────────────────────────────────────────────────

    def kill(self) -> None:
        self._kill_flag = True
        self._broadcast({"type": "killed"})

    def reset_kill(self) -> None:
        self._kill_flag = False

    def check_kill(self) -> bool:
        return self._kill_flag

    def set_cycle_running(self, running: bool) -> None:
        self._cycle_running = running
        self._broadcast({"type": "cycle_state", "running": running})

    # ── SSE ───────────────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def _broadcast(self, event: dict) -> None:
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    # ── Snapshot for REST ─────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        return {
            "panels": {**self._panels, **self._custom_panels},
            "messages": self._messages[-50:],
            "feedback_pending": self._feedback_pending,
            "feedback_question": self._feedback_question if self._feedback_pending else "",
            "cycle_running": self._cycle_running,
            "kill_flag": self._kill_flag,
        }


# Singleton
ui = UIState()

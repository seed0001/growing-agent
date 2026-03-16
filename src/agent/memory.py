"""
Short-term and working memory.
Short-term: rolling window of recent events (strings).
Working: key/value scratchpad for active task state.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

SHORT_TERM_MAX = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Memory:
    def __init__(self, memory_dir: Path):
        self._dir = Path(memory_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._st_path = self._dir / "short_term.json"
        self._wk_path = self._dir / "working.json"
        self._short_term: list[str] = []
        self._working: dict = {}
        self._load()

    def _load(self) -> None:
        if self._st_path.exists():
            try:
                self._short_term = json.loads(self._st_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._short_term = []
        if self._wk_path.exists():
            try:
                self._working = json.loads(self._wk_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._working = {}

    def _save_st(self) -> None:
        self._st_path.write_text(json.dumps(self._short_term, indent=2), encoding="utf-8")

    def _save_wk(self) -> None:
        self._wk_path.write_text(json.dumps(self._working, indent=2), encoding="utf-8")

    def add(self, text: str) -> None:
        """Append to short-term memory, pruning oldest if over limit."""
        self._short_term.append(text)
        if len(self._short_term) > SHORT_TERM_MAX:
            self._short_term = self._short_term[-SHORT_TERM_MAX:]
        self._save_st()

    def get_recent(self, n: int = 10) -> list[str]:
        return self._short_term[-n:]

    def set_working(self, key: str, value) -> None:
        if value is None:
            self._working.pop(key, None)
        else:
            self._working[key] = value
        self._save_wk()

    def get_working(self, key: str, default=None):
        return self._working.get(key, default)

    def get_working_view(self) -> dict:
        return dict(self._working)

    def context_block(self) -> str:
        """Recent memory formatted for the system prompt."""
        recent = self.get_recent(12)
        if not recent:
            return ""
        return "## Recent activity\n" + "\n".join(f"- {e}" for e in recent)

"""
Hull-style biological drives.
Accumulate over time, reduce on satisfaction.
D(t+dt) = D(t) + dt * rate — satisfaction_drop on event.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

DRIVES = ("connection", "curiosity", "usefulness", "expression")

RATE_PER_SEC       = 0.0001   # ~0.85/day to saturate
SATISFACTION_DROP  = 0.4
THRESHOLD_PROACTIVE = 0.65
MAX_DRIVE = 1.0
MIN_DRIVE = 0.0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


class DriveState:
    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.drives: dict[str, float] = {d: 0.0 for d in DRIVES}
        self.last_satisfaction: dict[str, str] = {}
        self.last_tick_at: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            for d in DRIVES:
                v = data.get("drives", {}).get(d)
                if isinstance(v, (int, float)):
                    self.drives[d] = max(MIN_DRIVE, min(MAX_DRIVE, float(v)))
            self.last_satisfaction = data.get("last_satisfaction") or {}
            self.last_tick_at = data.get("last_tick_at")
        except (OSError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "drives": self.drives,
                    "last_satisfaction": self.last_satisfaction,
                    "last_tick_at": self.last_tick_at,
                    "updated_at": _now_utc().isoformat(),
                },
                f, indent=2,
            )

    def _ensure_ticked(self) -> None:
        prev = _parse_iso(self.last_tick_at)
        now = _now_utc()
        if prev is None:
            self.last_tick_at = now.isoformat()
            self._save()
            return
        dt = (now - prev).total_seconds()
        if dt > 0:
            for d in DRIVES:
                self.drives[d] = min(MAX_DRIVE, self.drives[d] + dt * RATE_PER_SEC)
            self.last_tick_at = now.isoformat()
            self._save()

    def satisfy(self, drive: str) -> None:
        if drive not in DRIVES:
            return
        self._ensure_ticked()
        self.drives[drive] = max(MIN_DRIVE, self.drives[drive] - SATISFACTION_DROP)
        self.last_satisfaction[drive] = _now_utc().isoformat()
        self._save()

    def get_summary(self) -> str:
        self._ensure_ticked()
        parts = []
        for d in DRIVES:
            v = self.drives[d]
            label = "high" if v >= THRESHOLD_PROACTIVE else "moderate" if v >= 0.4 else "low"
            parts.append(f"{d}: {v:.2f} ({label})")
        return "Drives: " + "; ".join(parts)

    def get_view(self) -> dict:
        self._ensure_ticked()
        return {"drives": dict(self.drives), "last_satisfaction": dict(self.last_satisfaction)}

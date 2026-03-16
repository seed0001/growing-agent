"""
Documentary narrator — Discovery Channel style.

Observes the organism from the outside. Speaks at key moments (cycle start/end,
tool absorbed, knowledge written) in third person. Uses the shared voice queue
with the narrator voice (Ryan). Does not block the evolution loop.
"""
from src.voice import queue_speak


def on_cycle_start(cycle: int) -> None:
    """Called when an evolution cycle begins."""
    queue_speak(
        f"Cycle {cycle}. Inside the organism, another evolution begins.",
        "narrator",
    )


def on_cycle_end(cycle: int, summary: str = "") -> None:
    """Called when an evolution cycle completes."""
    preview = (summary or "").strip()[:120]
    if preview:
        queue_speak(
            f"The cycle closes. {preview}",
            "narrator",
        )
    else:
        queue_speak(
            f"Cycle {cycle} complete. The organism rests until the next trigger.",
            "narrator",
        )


def on_tool_absorbed(name: str) -> None:
    """Called when the organism successfully absorbs a new tool."""
    queue_speak(
        f"A new capability is integrated. {name} is now part of the organism.",
        "narrator",
    )


def on_knowledge_written(topic: str) -> None:
    """Called when the organism writes a knowledge entry."""
    queue_speak(
        f"Something is committed to memory. {topic}.",
        "narrator",
    )


def on_cycle_killed(cycle: int) -> None:
    """Called when the user kills the cycle."""
    queue_speak(
        "The cycle is interrupted. The organism goes quiet.",
        "narrator",
    )

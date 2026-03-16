"""
Self-growing knowledge base.

The agent writes here as it discovers things — how tools behave, what works,
what doesn't, patterns worth remembering. Starts empty. Grows through use.

Data: data/knowledge/<topic>.md
"""
import re
from datetime import datetime
from pathlib import Path

from config.settings import KNOWLEDGE_DIR


def _slug(topic: str) -> str:
    s = topic.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "_", s)
    return s[:80]


def _load_all() -> dict[str, dict]:
    entries = {}
    if not KNOWLEDGE_DIR.exists():
        return entries
    for p in KNOWLEDGE_DIR.glob("*.md"):
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
            updated_at = None
            content = raw
            if raw.startswith("---updated:"):
                lines = raw.split("\n", 2)
                if len(lines) >= 3:
                    updated_at = lines[0].replace("---updated:", "").strip()
                    content = lines[2]
            entries[p.stem] = {"content": content.strip(), "updated_at": updated_at}
        except OSError:
            continue
    return entries


def write_knowledge(topic: str, content: str, append: bool = False) -> str:
    topic = topic.strip()
    content = content.strip()
    if not topic:
        return "Error: topic name required."
    if not content:
        return "Error: content required."
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    key = _slug(topic)
    path = KNOWLEDGE_DIR / f"{key}.md"
    now = datetime.now().isoformat(timespec="seconds")
    if append and path.exists():
        existing = _load_all().get(key, {}).get("content", "")
        content = existing.rstrip() + "\n\n" + content
    path.write_text(f"---updated:{now}\n---\n{content}", encoding="utf-8")
    return f"Knowledge written: '{key}' ({len(content)} chars)"


def read_knowledge(topic: str) -> str:
    entries = _load_all()
    key = _slug(topic)
    if key in entries:
        e = entries[key]
        header = f"# {key}\n" + (f"_updated: {e['updated_at']}_\n\n" if e.get("updated_at") else "\n")
        return header + e["content"]
    for name, e in entries.items():
        if key in name or name in key:
            header = f"# {name}\n" + (f"_updated: {e['updated_at']}_\n\n" if e.get("updated_at") else "\n")
            return header + e["content"]
    avail = ", ".join(sorted(entries.keys())) if entries else "none yet"
    return f"No entry for '{topic}'. Available: {avail}"


def search_knowledge(query: str, max_results: int = 3) -> str:
    entries = _load_all()
    if not entries:
        return "Knowledge base is empty. Use write_knowledge to start building it."
    words = [w for w in query.lower().split() if len(w) > 2]
    if not words:
        return "Query too short."
    scored = []
    for name, e in entries.items():
        cl = e["content"].lower()
        score = sum((4 if w in name else 0) + cl.count(w) for w in words)
        if score > 0:
            scored.append((score, name, e))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return f"No matches for '{query}'. Topics: " + ", ".join(sorted(entries.keys()))
    parts = []
    for _, name, e in scored[:max_results]:
        hdr = f"## {name}" + (f"  _(updated {e['updated_at']})_" if e.get("updated_at") else "")
        parts.append(f"{hdr}\n{e['content']}")
    return "\n\n---\n\n".join(parts)


def list_knowledge_topics() -> str:
    entries = _load_all()
    if not entries:
        return "Knowledge base is empty."
    lines = [f"- {n}  (updated: {e.get('updated_at', '?')})" for n, e in sorted(entries.items())]
    return f"Knowledge base ({len(entries)} entries):\n" + "\n".join(lines)


def delete_knowledge(topic: str) -> str:
    key = _slug(topic)
    path = KNOWLEDGE_DIR / f"{key}.md"
    if path.exists():
        path.unlink()
        return f"Deleted: '{key}'"
    return f"No entry found for '{topic}'."

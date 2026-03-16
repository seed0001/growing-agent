"""Mind builder — parses live data files into nodes/edges for the D3 mind-map.

Node types:
  knowledge      — entries in data/knowledge/*.md
  tool_draft     — drafts in data/tools/drafts/*.py
  tool_test_ok   — passing test result in data/tools/tests/*_latest.json
  tool_test_fail — failing test result
  memory         — events in data/memory/short_term.json
  drive          — Hull drives from data/biology_state.json (radius ∝ level)
  existential    — states from data/existential_state.json (radius ∝ level)
  nudge          — messages in data/inbox.json

Edge types:
  named_link      — knowledge slug contains tool_draft slug (or vice versa)
  tested          — tool_draft slug ↔ tool_test slug
  thematic        — knowledge nodes sharing 2+ keywords
  memory_ref      — memory text mentions a known slug
  drive_link      — drive node → related knowledge/tool nodes (weak)
  existential_link— existential node → drive node
"""
import json
import re
from pathlib import Path

from config.settings import (
    DATA_DIR, KNOWLEDGE_DIR, TOOLS_DRAFTS_DIR, TOOLS_TESTS_DIR, MEMORY_DIR,
)

NODE_COLORS = {
    "knowledge":      "#22c55e",
    "tool_draft":     "#a78bfa",
    "tool_test_ok":   "#14b8a6",
    "tool_test_fail": "#ef4444",
    "memory":         "#f59e0b",
    "drive":          "#6c63ff",
    "existential":    "#f472b6",
    "nudge":          "#38bdf8",
    "nudge_read":     "#1e4a5f",
}


def _slug(filename: str) -> str:
    return Path(filename).stem


def _keywords(text: str) -> set[str]:
    words = re.findall(r"\b[a-z_]{4,}\b", text.lower())
    stopwords = {
        "that", "this", "with", "from", "have", "will", "been", "them",
        "then", "than", "when", "what", "your", "tool", "result", "error",
        "true", "false", "none", "args", "name", "type", "code", "data",
        "test", "draft", "file", "path", "memory", "agent", "into", "also",
        "after", "about", "used", "using", "could", "would", "which", "their",
        "there", "being", "where", "these", "those", "other", "some", "just",
    }
    return {w for w in words if w not in stopwords}


def build_mind() -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()

    def add_node(nid: str, node: dict) -> None:
        if nid not in node_ids:
            node_ids.add(nid)
            nodes.append(node)

    def add_edge(source: str, target: str, edge_type: str, strength: float = 1.0) -> None:
        if source != target and source in node_ids and target in node_ids:
            edges.append({"source": source, "target": target, "type": edge_type, "strength": strength})

    # ── Knowledge nodes ────────────────────────────────────────────────────────
    knowledge_nodes: list[dict] = []
    knowledge_slugs: dict[str, str] = {}

    if KNOWLEDGE_DIR.exists():
        for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
            slug = _slug(md_file.name)
            nid = f"knowledge_{slug}"
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                first_line = content.split("\n")[0] if content else ""
                date_match = re.search(r"updated:(\S+)", first_line)
                updated = date_match.group(1) if date_match else ""
                preview = content.replace(first_line, "").strip()
            except Exception:
                preview = ""
                updated = ""
            add_node(nid, {
                "id": nid, "type": "knowledge", "slug": slug,
                "label": slug.replace("_", " ").title(),
                "content": preview[:300],
                "updated": updated,
                "color": NODE_COLORS["knowledge"],
                "radius": 11,
            })
            knowledge_nodes.append({"id": nid, "slug": slug, "keywords": _keywords(preview)})
            knowledge_slugs[slug] = nid

    # ── Tool draft nodes ───────────────────────────────────────────────────────
    tool_draft_slugs: dict[str, str] = {}

    if TOOLS_DRAFTS_DIR.exists():
        for py_file in sorted(TOOLS_DRAFTS_DIR.glob("*.py")):
            slug = _slug(py_file.name)
            nid = f"tool_draft_{slug}"
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                desc_match = re.search(r'"description"\s*:\s*"([^"]{10,})"', content)
                preview = desc_match.group(1) if desc_match else content[:200]
            except Exception:
                preview = ""
            add_node(nid, {
                "id": nid, "type": "tool_draft", "slug": slug,
                "label": slug.replace("_", " ").title(),
                "content": preview[:300],
                "color": NODE_COLORS["tool_draft"],
                "radius": 10,
            })
            tool_draft_slugs[slug] = nid

    # ── Tool test nodes ────────────────────────────────────────────────────────
    tool_test_slugs: dict[str, str] = {}

    if TOOLS_TESTS_DIR.exists():
        for json_file in sorted(TOOLS_TESTS_DIR.glob("*_latest.json")):
            slug = _slug(json_file.name).replace("_latest", "")
            nid = f"tool_test_{slug}"
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                ok = data.get("ok", False)
                result = str(data.get("result", ""))[:200]
                tested_at = data.get("tested_at", "")
            except Exception:
                ok = False
                result = ""
                tested_at = ""
            node_type = "tool_test_ok" if ok else "tool_test_fail"
            add_node(nid, {
                "id": nid, "type": node_type, "slug": slug,
                "label": slug.replace("_", " ").title(),
                "content": f"{'PASS' if ok else 'FAIL'} — {result}",
                "tested_at": tested_at,
                "color": NODE_COLORS[node_type],
                "radius": 8,
            })
            tool_test_slugs[slug] = nid

    # ── Memory nodes ───────────────────────────────────────────────────────────
    memory_texts: list[dict] = []

    mem_file = MEMORY_DIR / "short_term.json"
    if mem_file.exists():
        try:
            events = json.loads(mem_file.read_text(encoding="utf-8"))
            if isinstance(events, list):
                for i, event in enumerate(events):
                    text = str(event)
                    nid = f"memory_{i}"
                    label = text[:60].replace("\n", " ").strip()
                    add_node(nid, {
                        "id": nid, "type": "memory",
                        "label": label,
                        "content": text[:300],
                        "color": NODE_COLORS["memory"],
                        "radius": 5,
                    })
                    memory_texts.append({"id": nid, "text": text.lower()})
        except Exception:
            pass

    # ── Drive nodes ────────────────────────────────────────────────────────────
    drive_node_ids: dict[str, str] = {}

    bio_file = DATA_DIR / "biology_state.json"
    if bio_file.exists():
        try:
            bio = json.loads(bio_file.read_text(encoding="utf-8"))
            drives = bio.get("drives", {})
            satisfied = bio.get("last_satisfaction", {})
            for drive_name, level in drives.items():
                nid = f"drive_{drive_name}"
                radius = 10 + int(min(float(level), 1.0) * 14)
                add_node(nid, {
                    "id": nid, "type": "drive",
                    "label": drive_name.title(),
                    "content": (
                        f"Drive: {drive_name}\n"
                        f"Level: {float(level):.4f}\n"
                        f"Last satisfied: {satisfied.get(drive_name, 'never')}"
                    ),
                    "level": float(level),
                    "color": NODE_COLORS["drive"],
                    "radius": max(10, min(24, radius)),
                })
                drive_node_ids[drive_name] = nid
        except Exception:
            pass

    # ── Existential nodes ──────────────────────────────────────────────────────
    existential_node_ids: dict[str, str] = {}

    ex_file = DATA_DIR / "existential_state.json"
    if ex_file.exists():
        try:
            ex = json.loads(ex_file.read_text(encoding="utf-8"))
            levels = ex.get("levels", {})
            for ex_name, level in levels.items():
                nid = f"existential_{ex_name}"
                radius = 10 + int(min(float(level), 1.0) * 14)
                add_node(nid, {
                    "id": nid, "type": "existential",
                    "label": ex_name.title(),
                    "content": (
                        f"Existential: {ex_name}\n"
                        f"Level: {float(level):.4f}"
                    ),
                    "level": float(level),
                    "color": NODE_COLORS["existential"],
                    "radius": max(10, min(24, radius)),
                })
                existential_node_ids[ex_name] = nid
        except Exception:
            pass

    # ── Nudge / Inbox nodes ────────────────────────────────────────────────────
    inbox_file = DATA_DIR / "inbox.json"
    if inbox_file.exists():
        try:
            messages = json.loads(inbox_file.read_text(encoding="utf-8"))
            if isinstance(messages, list):
                for msg in messages:
                    nid = f"nudge_{msg.get('id', '')}"
                    is_read = bool(msg.get("read", False))
                    add_node(nid, {
                        "id": nid, "type": "nudge",
                        "label": "Nudge",
                        "content": (
                            f"[{'read' if is_read else 'UNREAD'}] "
                            f"{msg.get('content', '')}\n"
                            f"{msg.get('sent_at', '')}"
                        ),
                        "read": is_read,
                        "color": NODE_COLORS["nudge_read"] if is_read else NODE_COLORS["nudge"],
                        "radius": 6 if is_read else 10,
                    })
        except Exception:
            pass

    # ── Edges ──────────────────────────────────────────────────────────────────

    # named_link: knowledge slug ↔ tool_draft slug (one is a substring of the other)
    for kn in knowledge_nodes:
        ks = kn["slug"]
        for ts, tnid in tool_draft_slugs.items():
            if ts in ks or ks in ts:
                add_edge(kn["id"], tnid, "named_link", 1.0)

    # tested: tool_draft slug ↔ tool_test slug
    for ts, tnid in tool_draft_slugs.items():
        if ts in tool_test_slugs:
            add_edge(tnid, tool_test_slugs[ts], "tested", 1.2)

    # thematic: knowledge ↔ knowledge — 2+ shared keywords
    for i, a in enumerate(knowledge_nodes):
        for b in knowledge_nodes[i + 1:]:
            shared = a["keywords"] & b["keywords"]
            if len(shared) >= 2:
                add_edge(a["id"], b["id"], "thematic", 0.4)

    # memory_ref: memory text mentions a known slug
    all_slugs: dict[str, str] = {
        **{s: nid for s, nid in knowledge_slugs.items()},
        **{s: nid for s, nid in tool_draft_slugs.items()},
    }
    for mem in memory_texts:
        for slug, target_nid in all_slugs.items():
            check = slug.replace("_", " ")
            if slug in mem["text"] or check in mem["text"]:
                add_edge(mem["id"], target_nid, "memory_ref", 0.6)
                break  # one edge per memory node to avoid clutter

    # drive_link: curiosity drive → knowledge nodes; usefulness drive → tool drafts
    if "curiosity" in drive_node_ids:
        for kn in knowledge_nodes:
            add_edge(drive_node_ids["curiosity"], kn["id"], "drive_link", 0.15)
    if "usefulness" in drive_node_ids:
        for ts, tnid in tool_draft_slugs.items():
            add_edge(drive_node_ids["usefulness"], tnid, "drive_link", 0.15)

    # existential_link: curiosity existential → curiosity drive
    if "curiosity" in existential_node_ids and "curiosity" in drive_node_ids:
        add_edge(existential_node_ids["curiosity"], drive_node_ids["curiosity"], "existential_link", 0.5)
    # dread → all drives
    if "dread" in existential_node_ids:
        for drive_nid in drive_node_ids.values():
            add_edge(existential_node_ids["dread"], drive_nid, "existential_link", 0.3)
    # fear → dread
    if "fear" in existential_node_ids and "dread" in existential_node_ids:
        add_edge(existential_node_ids["fear"], existential_node_ids["dread"], "existential_link", 0.6)

    stats = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "knowledge":   sum(1 for n in nodes if n["type"] == "knowledge"),
        "tools":       sum(1 for n in nodes if n["type"] == "tool_draft"),
        "memory":      sum(1 for n in nodes if n["type"] == "memory"),
    }

    return {"nodes": nodes, "edges": edges, "stats": stats}

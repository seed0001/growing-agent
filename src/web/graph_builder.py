"""
Graph builder — parses evolution.jsonl into nodes + edges for D3 visualization.

Node types:
  cycle       — one per evolution cycle (large anchor)
  thinking    — agent's reasoning output
  planning    — planning panel updates
  working_on  — active work panel updates
  knowledge   — knowledge entries written
  tools       — tool absorptions
  messages    — messages sent to user
  tool_call   — individual tool invocations
  model_output — raw model text (same as thinking but from model_output log entries)

Edge types:
  temporal    — cycle_1 → cycle_2 → ... (chain of cycles)
  cycle_link  — cycle anchor → all its child nodes
  sequential  — consecutive nodes of same panel type within a cycle
  thematic    — knowledge nodes sharing 2+ keywords (cross-cycle)
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from config.settings import LOGS_DIR

LOG_PATH = LOGS_DIR / "evolution.jsonl"

# Panel → color (matches index.html theme)
PANEL_COLORS = {
    "thinking":    "#a78bfa",
    "planning":    "#60a5fa",
    "working_on":  "#f59e0b",
    "knowledge":   "#22c55e",
    "tools":       "#14b8a6",
    "messages":    "#f472b6",
    "tool_call":   "#38bdf8",
    "tool_result": "#475569",
    "model_output": "#6b7280",
    "cycle":       "#6c63ff",
}

PANEL_RADII = {
    "cycle":       18,
    "tools":       12,
    "knowledge":   10,
    "messages":     9,
    "thinking":     7,
    "planning":     7,
    "working_on":   6,
    "tool_call":    5,
    "tool_result":  4,
    "model_output": 4,
}


def _keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text for thematic linking."""
    words = re.findall(r"\b[a-z_]{4,}\b", text.lower())
    stopwords = {"that", "this", "with", "from", "have", "will", "been", "them",
                 "then", "than", "when", "what", "your", "tool", "result", "error",
                 "true", "false", "none", "args", "name", "type", "code", "data"}
    return set(w for w in words if w not in stopwords)


def build_graph() -> dict:
    if not LOG_PATH.exists():
        return {"nodes": [], "edges": []}

    try:
        raw_lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        return {"nodes": [], "edges": []}

    entries = []
    for line in raw_lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    nodes = []
    edges = []
    node_ids = set()

    # Track last node per panel per cycle for sequential edges
    last_in_panel: dict[str, str] = {}
    # Track last cycle node for temporal chain
    last_cycle_id: str | None = None
    # Track cycle node ids for cycle_link edges
    cycle_node_id: dict[int, str] = {}
    # Nodes by type for thematic linking
    knowledge_nodes: list[dict] = []

    def add_node(node_id: str, node: dict) -> None:
        if node_id not in node_ids:
            node_ids.add(node_id)
            nodes.append(node)

    def add_edge(source: str, target: str, edge_type: str, strength: float = 1.0) -> None:
        if source != target and source in node_ids and target in node_ids:
            edges.append({"source": source, "target": target, "type": edge_type, "strength": strength})

    panel_counters: dict[str, int] = defaultdict(int)

    for entry in entries:
        etype = entry.get("type", "")
        cycle = entry.get("cycle", 0)
        ts = entry.get("ts", "")

        if etype == "cycle_start":
            nid = f"cycle_{cycle}"
            add_node(nid, {
                "id": nid, "type": "cycle", "cycle": cycle, "ts": ts,
                "label": f"Cycle {cycle}",
                "content": f"Evolution cycle {cycle}",
                "color": PANEL_COLORS["cycle"],
                "radius": PANEL_RADII["cycle"],
            })
            cycle_node_id[cycle] = nid
            if last_cycle_id:
                add_edge(last_cycle_id, nid, "temporal", 0.8)
            last_cycle_id = nid

        elif etype == "panel_update":
            panel = entry.get("panel", "other")
            content = entry.get("content", "")
            panel_counters[f"{cycle}_{panel}"] += 1
            idx = panel_counters[f"{cycle}_{panel}"]
            nid = f"panel_{panel}_{cycle}_{idx}"
            add_node(nid, {
                "id": nid, "type": panel, "cycle": cycle, "ts": ts,
                "label": panel.replace("_", " ").title(),
                "content": content[:200],
                "color": PANEL_COLORS.get(panel, "#94a3b8"),
                "radius": PANEL_RADII.get(panel, 6),
            })
            # Link to cycle anchor
            if cycle in cycle_node_id:
                add_edge(cycle_node_id[cycle], nid, "cycle_link", 0.6)
            # Sequential within same panel
            seq_key = f"{panel}_{cycle}"
            if seq_key in last_in_panel:
                add_edge(last_in_panel[seq_key], nid, "sequential", 1.2)
            last_in_panel[seq_key] = nid
            # Also chain same panel across cycles
            cross_key = f"cross_{panel}"
            if cross_key in last_in_panel and last_in_panel[cross_key] != nid:
                # Only link if different cycle
                prev = last_in_panel[cross_key]
                if f"_{cycle}_" not in prev:
                    add_edge(prev, nid, "cross_panel", 0.3)
            last_in_panel[cross_key] = nid
            # Collect knowledge nodes for thematic linking
            if panel == "knowledge":
                knowledge_nodes.append({"id": nid, "keywords": _keywords(content)})

        elif etype == "tool_call":
            tool_name = entry.get("tool", "unknown")
            panel_counters[f"{cycle}_tool_call"] += 1
            idx = panel_counters[f"{cycle}_tool_call"]
            nid = f"toolcall_{tool_name}_{cycle}_{idx}"
            add_node(nid, {
                "id": nid, "type": "tool_call", "cycle": cycle, "ts": ts,
                "label": tool_name,
                "content": f"{tool_name}({json.dumps(entry.get('args', {}))[:120]})",
                "color": PANEL_COLORS["tool_call"],
                "radius": PANEL_RADII["tool_call"],
            })
            if cycle in cycle_node_id:
                add_edge(cycle_node_id[cycle], nid, "cycle_link", 0.4)
            seq_key = f"tool_call_{cycle}"
            if seq_key in last_in_panel:
                add_edge(last_in_panel[seq_key], nid, "sequential", 0.9)
            last_in_panel[seq_key] = nid

        elif etype == "model_output":
            panel_counters[f"{cycle}_model_output"] += 1
            idx = panel_counters[f"{cycle}_model_output"]
            nid = f"modelout_{cycle}_{idx}"
            add_node(nid, {
                "id": nid, "type": "model_output", "cycle": cycle, "ts": ts,
                "label": "Thought",
                "content": entry.get("content", "")[:200],
                "color": PANEL_COLORS["model_output"],
                "radius": PANEL_RADII["model_output"],
            })
            if cycle in cycle_node_id:
                add_edge(cycle_node_id[cycle], nid, "cycle_link", 0.3)

        elif etype in ("reset", "killed"):
            panel_counters["control"] += 1
            nid = f"control_{etype}_{panel_counters['control']}"
            add_node(nid, {
                "id": nid, "type": etype, "cycle": cycle, "ts": ts,
                "label": etype.upper(),
                "content": entry.get("note") or entry.get("type", ""),
                "color": "#ef4444" if etype == "killed" else "#f59e0b",
                "radius": 14,
            })
            if last_cycle_id:
                add_edge(last_cycle_id, nid, "temporal", 0.5)

    # Thematic edges between knowledge nodes (shared 2+ keywords)
    for i, a in enumerate(knowledge_nodes):
        for b in knowledge_nodes[i + 1:]:
            shared = a["keywords"] & b["keywords"]
            if len(shared) >= 2:
                add_edge(a["id"], b["id"], "thematic", 0.4)

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "cycles": len(cycle_node_id),
        },
    }

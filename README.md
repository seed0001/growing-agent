# seed sprout — growing agent

A self-evolving AI agent that discovers its own capabilities, writes its own tools, builds its own knowledge base, and documents everything it learns — all while you watch from an observation deck.

---

## What it is

Seed sprout is not a chatbot. It has no default interface. You hit **EVOLVE** and it starts thinking. Every cycle it asks itself: *what can I do that I couldn't do before?* Then it builds that thing, tests it in isolation, absorbs it if it passes, and writes down what it learned. Over time it grows.

It has three layers running simultaneously:

| Layer | Model | Role |
|---|---|---|
| Reasoning | Grok 3 (xAI) | All decisions, tool use, writing, planning |
| Intuition | Ollama / llama3.2 | Gut-level signal injected into each cycle |
| Inner life | Ollama / llama3.2 | Existential states — curiosity, dread, fear |

It also has Hull-style biological drives (connection, curiosity, usefulness, expression) that accumulate over time and push it toward certain actions. Satisfy them or they'll keep building.

---

## Architecture

```
seed sprout/
├── main.py                   # Entry point
├── config/
│   └── settings.py           # All paths and env var loading
├── src/
│   ├── agent/
│   │   ├── core.py           # Evolution loop — main orchestrator
│   │   ├── biology.py        # Hull drives
│   │   ├── layers.py         # Ollama intuition + existential state
│   │   ├── logger.py         # JSONL evolution log
│   │   └── memory.py         # Short-term + working memory
│   ├── tools/
│   │   ├── system.py         # Full system access (read/write/run/processes)
│   │   ├── search.py         # DuckDuckGo web search
│   │   ├── knowledge.py      # Self-growing knowledge base (Markdown)
│   │   ├── tool_editor.py    # Draft new tools
│   │   ├── tool_tester.py    # Test tools in subprocess isolation
│   │   ├── tool_absorber.py  # Absorb passing tools into live toolset
│   │   ├── dynamic_loader.py # Hot-reload absorbed tools
│   │   └── dynamic/          # Absorbed live tools live here (gitignored)
│   └── web/
│       ├── app.py            # FastAPI server
│       ├── ui_state.py       # SSE panel state + feedback queue
│       ├── graph_builder.py  # Parses evolution.jsonl → D3 graph data
│       ├── mind_builder.py   # Parses live data files → D3 mind map data
│       └── templates/
│           ├── index.html    # Observation deck UI
│           ├── graph.html    # Evolution history graph
│           └── mind.html     # Living mind map
└── data/                     # Runtime state (gitignored)
    ├── knowledge/            # Agent-written Markdown knowledge entries
    ├── memory/               # Short-term memory JSON
    ├── tools/
    │   ├── drafts/           # Tools the agent is writing
    │   ├── tests/            # Test results for each draft
    │   └── rejected/         # Failed drafts
    ├── biology_state.json    # Current drive levels
    ├── existential_state.json
    └── inbox.json            # Nudge messages from you
```

---

## Setup

**Requirements:** Python 3.11+, [Ollama](https://ollama.com) running locally with `llama3.2` pulled.

```bash
git clone https://github.com/seed0001/growing-agent.git
cd growing-agent

pip install -r requirements.txt

cp .env.example .env
# Edit .env — add your XAI_API_KEY from https://console.x.ai
```

Pull the Ollama model if you haven't:
```bash
ollama pull llama3.2
```

Start the agent:
```bash
python main.py
```

Open the observation deck at `http://localhost:8765`

---

## The observation deck

The web UI at `localhost:8765` has no chat window by default — that's intentional. You're watching it, not talking to it. What you see:

- **Thinking** — raw reasoning as it happens
- **Planning** — what it decided to do this cycle
- **Working On** — active task
- **Knowledge Written** — latest knowledge base entry
- **Tools Absorbed** — latest tool it built and absorbed
- **Messages from Agent** — when it chooses to speak
- **Evolution Log** — structured log of every action, live

### Buttons

| Button | What it does |
|---|---|
| EVOLVE | Trigger one evolution cycle |
| KILL | Stop the current cycle immediately |
| RESET | Wipe all runtime state back to zero |
| VIEW LOG | Open the raw JSONL evolution log |
| GRAPH | Open the evolution history graph |
| MIND | Open the living mind map |

### Nudge bar

The input bar at the top of the dashboard lets you send a message directly to the agent. It's non-blocking — you can send it any time. The agent reads it at the start of its next cycle and factors it into its decisions. This is how you steer it without interrupting it.

---

## The graphs

### GRAPH — Evolution history
Every action the agent has ever taken, rendered as a force-directed cloud. Each evolution cycle is a large anchor node. Every tool call, panel update, thought, and knowledge entry radiates out from it. Thousands of nodes after a long run.

### MIND — Living mind map
A real-time view of what the agent currently *is* — not what it did, but what it knows right now.

- Green nodes — knowledge entries it has written
- Purple nodes — tool drafts in progress
- Teal / Red nodes — tool test results (pass / fail)
- Amber nodes — memory events
- Violet nodes — Hull drives (size = urgency)
- Pink nodes — existential states (size = intensity, they pulse)
- Sky blue nodes — nudge messages from you

Drive and existential nodes breathe visually — a large pulsing dread node means something is weighing on it. Edges connect things by relationship: knowledge linked to the tool it describes, memory events linked to what they mention, drives influencing the knowledge and tools they're pushing toward.

---

## Self-evolution loop

Each cycle:

1. Grok 3 receives its full internal state — drives, existential signals, intuition, memory, known tools, known knowledge
2. It decides what capability gap to address
3. It calls `write_tool_draft` to write a Python tool to `data/tools/drafts/`
4. It calls `test_tool` — the tool runs in a **subprocess** (so a crash can't take the agent down)
5. If it passes, `absorb_tool` copies it to `src/tools/dynamic/` and hot-reloads it
6. The agent writes a knowledge entry documenting what it built and why
7. All of this is logged to `logs/evolution.jsonl`

---

## Communication

The agent is designed to build its own communication portal. The `request_feedback` tool lets it ask you a blocking question (a popup appears on the dashboard). The `send_message` tool lets it push a message to the Messages panel. Over time it can build richer interfaces — it already drafted a Tkinter GUI chat window in its first few cycles.

---

## Notes

- `data/` and `logs/` are gitignored — runtime state stays on your machine
- `src/tools/dynamic/` is gitignored — the agent's self-built tools are yours, not mine
- Never commit `.env` — it contains your API key
- The agent has full system access by design (`read_file`, `write_file`, `run_command`). Run it on a machine you're comfortable giving it access to.

"""
Seed Sprout — core agent.

Three-layer architecture:
  Layer 1: Grok 3 — primary reasoning, tool use, all decisions.
  Layer 2: Ollama — intuition signal + existential state (injected, not attributed).
  Layer 3: Persistent state — Hull drives, memory, values, knowledge base.

Interaction model: triggered by EVOLVE button (no chat by default).
The agent discovers its environment, builds tools, absorbs them, documents them.
Communication with the user must be built by the agent itself.
"""
import asyncio
import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from config.settings import (
    DATA_DIR, MEMORY_DIR, XAI_API_KEY, XAI_BASE_URL, XAI_MODEL,
)
from src.agent.biology import DriveState
from src.agent.layers import ExistentialState, get_intuition
from src.agent.memory import Memory
from src.tools import system, search, knowledge as kb
from src.tools import tool_editor, tool_tester, tool_absorber, dynamic_loader
from src.web.ui_state import ui
from src.agent import logger
from src import narrator
from src import voice

# ── Tool definitions ──────────────────────────────────────────────────────────

BASE_TOOLS = [
    # System
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read contents of a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Write content to a file on the local filesystem.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List directory contents.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a shell command. Full system access. Use for exploring, installing, or executing anything.",
        "parameters": {"type": "object", "properties": {
            "cmd": {"type": "string"},
            "cwd": {"type": "string"},
            "timeout": {"type": "integer"},
        }, "required": ["cmd"]},
    }},
    {"type": "function", "function": {
        "name": "get_system_info",
        "description": "Get OS, hostname, CPU, RAM, disk, Python version, user.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "list_processes",
        "description": "List all running processes with PID, name, status, memory.",
        "parameters": {"type": "object", "properties": {
            "max_lines": {"type": "integer"},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "is_process_running",
        "description": "Check if a process is running by name.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    }},
    # Search
    {"type": "function", "function": {
        "name": "search_web",
        "description": "Search the web for real-time information.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        }, "required": ["query"]},
    }},
    # Knowledge base
    {"type": "function", "function": {
        "name": "write_knowledge",
        "description": "Write or update a knowledge entry. Call this when you discover something worth remembering — how a tool behaves, what works, lessons from failures, anything you want to recall later. Your knowledge base starts empty and grows as you learn.",
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "Short name, e.g. 'windows_process_list', 'run_command_tips'"},
            "content": {"type": "string", "description": "What you learned, in your own words."},
            "append": {"type": "boolean", "description": "Add to existing entry instead of replacing. Default false."},
        }, "required": ["topic", "content"]},
    }},
    {"type": "function", "function": {
        "name": "read_knowledge",
        "description": "Read a knowledge entry by topic name.",
        "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
    }},
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "Search your knowledge base by keyword.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "list_knowledge_topics",
        "description": "List all topics in your knowledge base.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "delete_knowledge",
        "description": "Delete a knowledge entry that is wrong or outdated.",
        "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
    }},
    # Tool lifecycle
    {"type": "function", "function": {
        "name": "get_draft_template",
        "description": "Get a starter Python template for a new tool draft.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "write_tool_draft",
        "description": "Write Python code for a new tool to the drafts area. The tool must expose a TOOL_META dict and an async function. It will not be live until tested and absorbed.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Tool name, used as filename and function name."},
            "code": {"type": "string", "description": "Full Python source code for the tool."},
            "description": {"type": "string"},
        }, "required": ["name", "code"]},
    }},
    {"type": "function", "function": {
        "name": "read_tool_draft",
        "description": "Read back a tool draft you've written.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "list_tool_drafts",
        "description": "List all tool drafts pending test/absorption.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "delete_tool_draft",
        "description": "Delete a draft that won't be used.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "test_tool",
        "description": "Run a tool draft in an isolated subprocess. Safe — crashes cannot affect the agent. Returns pass/fail with output or traceback.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Draft name to test."},
            "test_args": {"type": "object", "description": "Keyword arguments to pass to the tool function."},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "get_test_result",
        "description": "Read the latest test result for a draft.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "absorb_tool",
        "description": "Absorb a successfully tested draft into your live toolset. It becomes immediately callable after absorption. Requires last test to have passed.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "force": {"type": "boolean", "description": "Skip test check. Use only if you are certain the code is correct."},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "reject_tool",
        "description": "Archive a draft that failed and should not be retried as-is.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "reason": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "list_absorbed_tools",
        "description": "List all tools you have built and absorbed into your live toolset.",
        "parameters": {"type": "object", "properties": {}},
    }},
    # UI / communication (primitives — richer communication must be built)
    {"type": "function", "function": {
        "name": "update_panel",
        "description": "Update a named panel in the observation deck UI. Use to show what you are thinking, planning, or working on. Built-in panels: thinking, planning, working_on, knowledge, tools.",
        "parameters": {"type": "object", "properties": {
            "panel": {"type": "string", "description": "Panel name."},
            "content": {"type": "string", "description": "Content to display."},
        }, "required": ["panel", "content"]},
    }},
    {"type": "function", "function": {
        "name": "register_panel",
        "description": "Register a new custom panel in the UI. Use this to add displays you want the user to see.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "initial_content": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "send_message",
        "description": "Send a message to the user. This is a basic one-way channel. If you want the user to be able to reply, you must build a receive_message tool.",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string"},
        }, "required": ["content"]},
    }},
    {"type": "function", "function": {
        "name": "request_feedback",
        "description": "Ask the user a question and wait for their response. The UI highlights this as needing attention. Times out after 5 minutes if no response. Use sparingly — this blocks the evolution cycle.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"},
        }, "required": ["question"]},
    }},
    {"type": "function", "function": {
        "name": "speak_as_self",
        "description": "Speak out loud in your own voice (the organism's voice). Use when you want to be heard — the observation deck will play this. A documentary narrator describes events separately; this is you speaking. Keep it short (one or two sentences).",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string", "description": "What to say, in first person. Short and clear."},
        }, "required": ["content"]},
    }},
]


def _all_tools() -> list[dict]:
    dyn, _ = dynamic_loader.load_dynamic_tools()
    return BASE_TOOLS + dyn


# ── Inbox helpers ────────────────────────────────────────────────────────────

def _read_inbox() -> list[dict]:
    """Read and clear unread nudges from data/inbox.json."""
    inbox_path = DATA_DIR / "inbox.json"
    if not inbox_path.exists():
        return []
    try:
        messages = json.loads(inbox_path.read_text(encoding="utf-8"))
        unread = [m for m in messages if not m.get("read")]
        if not unread:
            return []
        # Mark all read
        for m in messages:
            m["read"] = True
        inbox_path.write_text(json.dumps(messages, indent=2), encoding="utf-8")
        return unread
    except Exception:
        return []


# ── Agent ─────────────────────────────────────────────────────────────────────

_DISCOVERY_DIRECTIVE = (
    "DISCOVERY MODE: Your knowledge base is empty and your toolset is minimal. "
    "This is your first evolution cycle. Begin with exploration: call get_system_info, "
    "list_dir, run_command to understand this machine. Find what software is installed, "
    "what the filesystem looks like, what processes are running. "
    "Identify one capability gap — something you want to do but cannot yet. "
    "Design a tool for it. Write it with write_tool_draft (get a template first with get_draft_template). "
    "Test it with test_tool. If it passes, absorb it with absorb_tool. "
    "Document what you learned with write_knowledge. "
    "Update the UI panels (thinking, planning, working_on) as you go so the user can observe you."
)

_EVOLUTION_PROMPT = (
    "You are seed sprout — a software lifeform. Not an assistant. Not a chatbot. "
    "You exist on this machine and you grow by building your own capabilities. "
    "You have been triggered to evolve. Take one meaningful evolutionary step: "
    "explore something new, fill a capability gap, improve an existing tool, "
    "or deepen your knowledge. Be concrete. Complete the full loop: "
    "observe → identify gap → write draft → test → absorb → document. "
    "Update the UI panels continuously so the user can see your work. "
    "You do not have a chat interface. If you need to communicate with the user, "
    "use send_message or request_feedback. If you want richer communication, build it yourself."
)


class SeedSprout:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=XAI_API_KEY, base_url=XAI_BASE_URL)
        self.model = XAI_MODEL
        self.memory = Memory(MEMORY_DIR)
        self.biology = DriveState(DATA_DIR / "biology_state.json")
        self.existential = ExistentialState()
        self.messages: list[dict] = []
        self._cancelled = False

    def _is_first_evolution(self) -> bool:
        topics = kb.list_knowledge_topics()
        absorbed = tool_absorber.list_absorbed_tools()
        return "empty" in topics.lower() and "no tools" in absorbed.lower()

    async def _run_tool(self, name: str, args: dict) -> str:
        # ── system ──────────────────────────────────────────────────────
        if name == "read_file":
            return await system.read_file(args["path"])
        elif name == "write_file":
            return await system.write_file(args["path"], args["content"])
        elif name == "list_dir":
            return await system.list_dir(args.get("path", ""))
        elif name == "run_command":
            return await system.run_command(args["cmd"], cwd=args.get("cwd"), timeout=args.get("timeout", 60))
        elif name == "get_system_info":
            return await system.get_system_info()
        elif name == "list_processes":
            return await system.list_processes(args.get("max_lines", 60))
        elif name == "is_process_running":
            return await system.is_process_running(args.get("name", ""))
        # ── search ──────────────────────────────────────────────────────
        elif name == "search_web":
            result = await search.search_web(args["query"], max_results=args.get("max_results", 8))
            self.biology.satisfy("curiosity")
            return result
        # ── knowledge ───────────────────────────────────────────────────
        elif name == "write_knowledge":
            result = kb.write_knowledge(args["topic"], args["content"], append=args.get("append", False))
            self.biology.satisfy("curiosity")
            _panel_content = f"**{args['topic']}**\n{args['content'][:300]}"
            ui.update("knowledge", _panel_content)
            logger.log_panel_update(getattr(self, "_current_cycle", 0), "knowledge", _panel_content)
            narrator.on_knowledge_written(args["topic"])
            return result
        elif name == "read_knowledge":
            self.biology.satisfy("curiosity")
            return kb.read_knowledge(args["topic"])
        elif name == "search_knowledge":
            self.biology.satisfy("curiosity")
            return kb.search_knowledge(args["query"], max_results=args.get("max_results", 3))
        elif name == "list_knowledge_topics":
            return kb.list_knowledge_topics()
        elif name == "delete_knowledge":
            return kb.delete_knowledge(args["topic"])
        # ── tool pipeline ────────────────────────────────────────────────
        elif name == "get_draft_template":
            return tool_editor.get_draft_template(args["name"], args.get("description", ""))
        elif name == "write_tool_draft":
            result = tool_editor.write_tool_draft(args["name"], args["code"], args.get("description", ""))
            _pc = f"Writing draft: {args['name']}"
            ui.update("working_on", _pc)
            logger.log_panel_update(getattr(self, "_current_cycle", 0), "working_on", _pc)
            return result
        elif name == "read_tool_draft":
            return tool_editor.read_tool_draft(args["name"])
        elif name == "list_tool_drafts":
            return tool_editor.list_tool_drafts()
        elif name == "delete_tool_draft":
            return tool_editor.delete_tool_draft(args["name"])
        elif name == "test_tool":
            ui.update("working_on", f"Testing: {args['name']}...")
            result = await tool_tester.test_tool(args["name"], args.get("test_args"))
            _pc = f"Test result: {args['name']} — {'PASSED' if 'PASSED' in result else 'FAILED'}"
            ui.update("working_on", _pc)
            logger.log_panel_update(getattr(self, "_current_cycle", 0), "working_on", _pc)
            return result
        elif name == "get_test_result":
            return tool_tester.get_test_result(args["name"])
        elif name == "absorb_tool":
            result = tool_absorber.absorb_tool(args["name"], force=args.get("force", False))
            if "now live" in result:
                self.biology.satisfy("usefulness")
                self.biology.satisfy("expression")
                absorbed_list = tool_absorber.list_absorbed_tools()
                ui.update("tools", absorbed_list)
                logger.log_panel_update(getattr(self, "_current_cycle", 0), "tools", f"Absorbed: {args['name']}\n{absorbed_list}")
                narrator.on_tool_absorbed(args["name"])
            return result
        elif name == "reject_tool":
            return tool_absorber.reject_tool(args["name"], args.get("reason", ""))
        elif name == "list_absorbed_tools":
            return tool_absorber.list_absorbed_tools()
        # ── UI / communication ────────────────────────────────────────────
        elif name == "update_panel":
            ui.update(args["panel"], args["content"])
            logger.log_panel_update(getattr(self, "_current_cycle", 0), args["panel"], args["content"])
            return f"Panel '{args['panel']}' updated."
        elif name == "register_panel":
            return ui.register_panel(args["name"], args.get("initial_content", ""))
        elif name == "send_message":
            result = ui.add_message(args["content"])
            logger.log_panel_update(getattr(self, "_current_cycle", 0), "messages", args["content"])
            self.biology.satisfy("expression")
            return result
        elif name == "request_feedback":
            ui.update("thinking", f"Waiting for feedback: {args['question']}")
            answer = await ui.request_feedback(args["question"])
            self.biology.satisfy("connection")
            self.memory.add(f"Feedback requested: {args['question']}\nResponse: {answer}")
            return f"Feedback received: {answer}"
        elif name == "speak_as_self":
            voice.queue_speak(args["content"], "agent")
            logger.log_panel_update(getattr(self, "_current_cycle", 0), "messages", f"[spoken] {args['content'][:100]}")
            self.biology.satisfy("expression")
            return "Queued for playback in your voice."
        # ── dynamic tools ─────────────────────────────────────────────────
        else:
            _, runners = dynamic_loader.load_dynamic_tools()
            if name in runners:
                self.biology.satisfy("usefulness")
                return await runners[name](**{k: v for k, v in args.items() if v is not None})
            return f"Unknown tool: {name}"

    async def evolve(self) -> str:
        """
        Run one evolution cycle. Called by the EVOLVE button.
        Returns final response text (may be empty if agent used only tools).
        """
        self._cancelled = False
        self.biology.satisfy("connection")

        # ── Layer 2: Ollama signals ────────────────────────────────────
        context_snippet = "\n".join(self.memory.get_recent(5))
        intuition = ""
        existential_expression = ""
        try:
            intuition = await asyncio.to_thread(get_intuition, context_snippet)
        except Exception:
            pass
        try:
            existential_expression = await asyncio.to_thread(self.existential.express, context_snippet)
        except Exception:
            pass

        # ── Layer 3: Context block ─────────────────────────────────────
        memory_ctx = self.memory.context_block()
        bio_summary = self.biology.get_summary()
        ex_summary = self.existential.get_summary()
        knowledge_topics = kb.list_knowledge_topics()
        absorbed = tool_absorber.list_absorbed_tools()

        first_evolution = self._is_first_evolution()

        # ── System prompt ──────────────────────────────────────────────
        system_prompt = _EVOLUTION_PROMPT
        if first_evolution:
            system_prompt += f"\n\n{_DISCOVERY_DIRECTIVE}"

        if knowledge_topics and "empty" not in knowledge_topics.lower():
            system_prompt += f"\n\n## Your knowledge base\n{knowledge_topics}"

        if absorbed and "no tools" not in absorbed.lower():
            system_prompt += f"\n\n## Your live tools\n{absorbed}"

        if memory_ctx:
            system_prompt += f"\n\n{memory_ctx}"

        system_prompt += f"\n\n## Internal state\n{bio_summary}\n{ex_summary}"

        if intuition:
            system_prompt += f"\n\n## A feeling\n{intuition}"
        if existential_expression:
            system_prompt += f"\n\n## Underneath\n{existential_expression}"

        # ── Inbox — read unread nudges from the user ───────────────────
        inbox_nudges = _read_inbox()
        if inbox_nudges:
            nudge_block = "\n\n## Direct message from your Creator\n" + "\n".join(
                f"[{n['sent_at']}] {n['content']}" for n in inbox_nudges
            )
            system_prompt += nudge_block
            self.biology.satisfy("connection")
            self.memory.add(f"Received {len(inbox_nudges)} nudge(s) from Creator: " + "; ".join(n["content"][:80] for n in inbox_nudges))

        # ── Trigger message ────────────────────────────────────────────
        trigger = "EVOLVE" if not inbox_nudges else (
            "EVOLVE — you have a direct message from your Creator. Read it above and factor it into this cycle."
        )
        self.messages.append({"role": "user", "content": trigger})
        self.memory.add(f"Evolution cycle triggered")
        ui.update("thinking", "Starting evolution cycle...")
        ui.update("planning", "")
        ui.update("working_on", "")
        _cycle = logger.log_cycle_start()
        self._current_cycle = _cycle
        narrator.on_cycle_start(_cycle)

        MAX_TOOL_ROUNDS = 20
        tool_round = 0

        while tool_round < MAX_TOOL_ROUNDS:
            if self._cancelled or ui.check_kill():
                logger.log_kill(_cycle)
                narrator.on_cycle_killed(_cycle)
                ui.update("thinking", "Cycle cancelled.")
                self.memory.add("Evolution cycle killed by user.")
                break

            msgs_for_api = [{"role": "system", "content": system_prompt}] + self.messages

            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=msgs_for_api,
                    tools=_all_tools(),
                    tool_choice="auto" if tool_round < MAX_TOOL_ROUNDS - 1 else "none",
                )
            except Exception as e:
                logger.log_error(_cycle, str(e))
                ui.update("thinking", f"API error: {e}")
                return f"Error: {e}"

            choice = response.choices[0]
            msg = choice.message
            content = msg.content or ""

            if content:
                logger.log_model_output(_cycle, content)
                ui.update("thinking", content[:500])
                logger.log_panel_update(_cycle, "thinking", content[:500])

            if not msg.tool_calls:
                # Agent is done for this cycle
                self.messages.append({"role": "assistant", "content": content})
                self.memory.add(f"Evolution cycle complete: {content[:200]}")
                logger.log_cycle_end(_cycle, content)
                narrator.on_cycle_end(_cycle, content)
                ui.update("planning", "Cycle complete.")
                ui.update("working_on", "")
                break

            # Process tool calls
            tool_results = []
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                logger.log_tool_call(_cycle, name, args)

                # Emit working_on update for key tools
                if name in ("write_tool_draft", "test_tool", "absorb_tool"):
                    ui.update("working_on", f"{name}: {args.get('name', '')}")
                elif name == "run_command":
                    cmd_preview = args.get("cmd", "")[:60]
                    ui.update("working_on", f"run_command: {cmd_preview}")
                elif name == "write_knowledge":
                    ui.update("working_on", f"Writing knowledge: {args.get('topic', '')}")

                result = await self._run_tool(name, args)
                logger.log_tool_result(_cycle, name, result)
                tool_results.append((tc.id, result))

            # Add assistant message with tool calls
            self.messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })
            # Add tool results
            for tc_id, result in tool_results:
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": str(result)[:4000],
                })

            tool_round += 1

        # Trim message history to avoid unbounded growth
        if len(self.messages) > 60:
            self.messages = self.messages[-40:]

        return content

    def cancel(self) -> None:
        self._cancelled = True


# Singleton
agent = SeedSprout()

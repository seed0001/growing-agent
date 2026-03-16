"""Configuration — seed sprout."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

KNOWLEDGE_DIR      = DATA_DIR / "knowledge"
TOOLS_DRAFTS_DIR   = DATA_DIR / "tools" / "drafts"
TOOLS_TESTS_DIR    = DATA_DIR / "tools" / "tests"
TOOLS_REJECTED_DIR = DATA_DIR / "tools" / "rejected"
DYNAMIC_TOOLS_DIR  = PROJECT_ROOT / "src" / "tools" / "dynamic"
MEMORY_DIR         = DATA_DIR / "memory"
LOGS_DIR           = PROJECT_ROOT / "logs"
FEEDBACK_FILE      = DATA_DIR / "feedback_queue.json"
INBOX_FILE         = DATA_DIR / "inbox.json"

for _d in (
    DATA_DIR, KNOWLEDGE_DIR, TOOLS_DRAFTS_DIR, TOOLS_TESTS_DIR,
    TOOLS_REJECTED_DIR, DYNAMIC_TOOLS_DIR, MEMORY_DIR, LOGS_DIR,
):
    _d.mkdir(parents=True, exist_ok=True)

# xAI Grok
XAI_API_KEY  = os.getenv("XAI_API_KEY", "")
XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MODEL    = os.getenv("XAI_MODEL", "grok-3")

# Ollama (inner life)
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Web
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8765"))

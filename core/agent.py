import os
import re
import ast
import json
import importlib
import inspect
import time
from dotenv import load_dotenv
load_dotenv()  # Load .env SEBELUM import tools

from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langchain_core.callbacks import BaseCallbackHandler

from core.logger import log_internal_step, log_token_usage

# ---------------------------------------------------------------------------
# Tool loading (with mtime-based caching + hot-reload + pre-import validation)
# ---------------------------------------------------------------------------

_BASE_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
_GENERATED_SKILLS_DIR = os.path.join(_BASE_SKILLS_DIR, "generated")

# Cache: {file_path: mtime} so we only re-import files that actually changed,
# instead of blindly importlib.import_module-ing (and never reloading) or
# reloading everything every single turn (v1's problem).
_tool_cache = {
    "tools": [],       # list[BaseTool]
    "file_mtimes": {},  # path -> last seen mtime
}

# ---------------------------------------------------------------------------
# Tool output size limiter (Opsi C)
# ---------------------------------------------------------------------------
# If a tool returns more than TOOL_OUTPUT_THRESHOLD chars, we save the full
# output to a timestamped file and return only a short summary to the LLM.
# This prevents huge HTML/JSON/log dumps from bloating the context window.

TOOL_OUTPUT_THRESHOLD = 1500  # chars - tune as needed
_LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def _wrap_tool_output(tool: BaseTool) -> BaseTool:
    """
    Wraps a BaseTool so that if its string output exceeds TOOL_OUTPUT_THRESHOLD,
    the full output is saved to a file and a compact summary is returned instead.
    The LLM only sees the summary + file path, keeping context window small.
    """
    original_run = tool._run

    def _run_with_limit(*args, config=None, run_manager=None, **kwargs):
        from datetime import datetime
        result = original_run(*args, config=config, run_manager=run_manager, **kwargs)
        result_str = str(result) if not isinstance(result, str) else result
        if len(result_str) <= TOOL_OUTPUT_THRESHOLD:
            return result_str
        # Save full output to file
        os.makedirs(_LOGS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = f"{tool.name}_{ts}.txt"
        fpath = os.path.join(_LOGS_DIR, fname)
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(result_str)
        except Exception:
            return result_str  # fallback: return as-is if save fails
        preview = result_str[:300].replace("\n", " ")
        return (
            f"[Output terlalu panjang: {len(result_str):,} chars]\n"
            f"✅ Sudah disimpan ke: logs/{fname}\n"
            f"Preview (300 chars pertama):\n{preview}..."
        )

    tool._run = _run_with_limit
    return tool


def _validate_skill_source(file_path: str) -> tuple[bool, str]:
    """
    Sanity-check a generated skill file BEFORE it's ever imported.
    We don't execute anything here - just parse the AST. This catches
    syntax errors and obviously-unsafe patterns without running untrusted
    code. It is NOT a full security sandbox, just a cheap first filter.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Could not read/parse file: {e}"

    # Require at least one function decorated with @tool - otherwise it's
    # not going to register as a BaseTool anyway, so no point importing it.
    has_tool_decorator = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                dec_name = dec.id if isinstance(dec, ast.Name) else getattr(dec, "attr", "")
                if dec_name == "tool":
                    has_tool_decorator = True

    if not has_tool_decorator:
        return False, "No @tool-decorated function found - refusing to import."

    return True, "ok"


def load_all_tools(force: bool = False):
    """
    Scan skills/ and skills/generated/ for *_skill.py files, validate them,
    import (or re-import if changed) them, and collect any BaseTool
    instances defined inside.

    Unlike the previous version, this:
      - actually reloads a module if the underlying file changed (mtime),
        so edits to a previously-broken generated skill take effect
        without restarting the process.
      - validates the file with ast.parse before importing it, so a
        malformed/unsafe-looking generated file doesn't get silently
        imported (and doesn't crash the whole tool-loading pass).
      - is cheap to call every turn: if nothing changed on disk, it
        returns the cached tool list instead of re-scanning imports.
    """
    dirs_to_scan = [
        (_BASE_SKILLS_DIR, "skills"),
        (_GENERATED_SKILLS_DIR, "skills.generated"),
    ]

    changed = force
    current_files = {}

    for directory, module_prefix in dirs_to_scan:
        if not os.path.exists(directory):
            continue
        for filename in os.listdir(directory):
            if not filename.endswith("_skill.py") or filename.startswith("__"):
                continue
            file_path = os.path.join(directory, filename)
            mtime = os.path.getmtime(file_path)
            current_files[file_path] = (mtime, module_prefix, filename)
            if _tool_cache["file_mtimes"].get(file_path) != mtime:
                changed = True

    # Also detect deletions (a file that was cached but no longer exists)
    if set(_tool_cache["file_mtimes"].keys()) - set(current_files.keys()):
        changed = True

    if not changed:
        return _tool_cache["tools"]

    dynamic_tools = []
    new_mtimes = {}

    for file_path, (mtime, module_prefix, filename) in current_files.items():
        module_name = f"{module_prefix}.{filename[:-3]}"

        ok, reason = _validate_skill_source(file_path)
        if not ok:
            print(f"[skills] Skipping {module_name}: {reason}")
            continue

        try:
            if module_name in importlib.sys.modules:
                module = importlib.reload(importlib.sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
        except Exception as e:
            print(f"[skills] Warning: failed to load {module_name}: {e}")
            continue

        for _, obj in inspect.getmembers(module):
            if isinstance(obj, BaseTool) and obj.name not in [t.name for t in dynamic_tools]:
                dynamic_tools.append(_wrap_tool_output(obj))

        new_mtimes[file_path] = mtime

    _tool_cache["tools"] = dynamic_tools
    _tool_cache["file_mtimes"] = new_mtimes
    return dynamic_tools


# ---------------------------------------------------------------------------
# Dynamic tool retrieval (keyword-based - no extra LLM round trip)
# ---------------------------------------------------------------------------
# v1 asked the LLM itself to list relevant tool names as free text, then
# parsed that with .split(","). That's an extra LLM call every single turn
# AND fragile (breaks the moment the model adds a sentence of preamble).
# Instead we score tools by simple keyword overlap between the user's
# query and each tool's name/description. It's not as smart as embeddings,
# but it's free, instant, deterministic, and "good enough" for narrowing
# down a large generated-skills folder so the main LLM call isn't dragging
# around 100 tool schemas it'll never use.

# Tools that must always be available regardless of the query - the agent's
# core capabilities (memory, guideline lookup) shouldn't ever get filtered
# out just because the wording of the query didn't happen to match them.
# CORE_TOOL_NAMES = {"remember_fact", "recall_facts", "forget_fact", "list_guidelines", "read_guideline"}
CORE_TOOL_NAMES = {"remember_fact", "recall_facts", "forget_fact"}

# Only bother filtering once the tool count gets large enough that context
# bloat is a real concern. Below this, just bind everything - filtering has
# no benefit and only risks accidentally hiding a tool the agent needed.
TOOL_FILTER_THRESHOLD = 15
MAX_RELEVANT_TOOLS = 12

_STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "ini", "itu", "the",
    "a", "an", "and", "or", "of", "to", "for", "is", "are", "aku", "kamu",
    "saya", "kau", "nya", "pada", "ada", "bisa", "gimana", "gak", "ga",
}


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def select_relevant_tools(all_tools: list, query: str) -> list:
    """
    Narrow `all_tools` down to the ones most likely relevant to `query`,
    using plain keyword overlap. Core tools are always kept. If there
    aren't enough tools to matter, or nothing scores above zero, falls
    back to returning everything (fail-open, not fail-closed - we'd
    rather bind a few extra unused tools than accidentally hide the one
    the agent actually needs).
    """
    if len(all_tools) <= TOOL_FILTER_THRESHOLD or not query:
        return all_tools

    query_tokens = _tokenize(query)
    if not query_tokens:
        return all_tools

    core = [t for t in all_tools if t.name in CORE_TOOL_NAMES]
    candidates = [t for t in all_tools if t.name not in CORE_TOOL_NAMES]

    scored = []
    for t in candidates:
        tool_tokens = _tokenize(t.name) | _tokenize(t.description or "")
        overlap = len(query_tokens & tool_tokens)
        # Extra weight if the tool name itself shows up in the query -
        # strong signal the user (or a prior turn) is referring to it directly.
        if t.name.lower().replace("_", " ") in query.lower():
            overlap += 3
        if overlap > 0:
            scored.append((overlap, t))

    if not scored:
        # Nothing matched at all - safer to return everything than to
        # silently strip the agent down to just the core tools.
        return all_tools

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [t for _, t in scored[:MAX_RELEVANT_TOOLS]]

    # Keep result order stable-ish and de-duplicated
    seen = set()
    result = []
    for t in core + top:
        if t.name not in seen:
            seen.add(t.name)
            result.append(t)
    return result


# ---------------------------------------------------------------------------
# Dynamic memory retrieval
# ---------------------------------------------------------------------------
# Unlike tool selection above, this is just a vector-DB lookup (not an LLM
# call), so it's cheap enough to run every turn like v1 did. Wrapped so a
# missing/broken memory_db never takes the whole agent down with it.

def retrieve_memories(query: str, k: int = 3) -> str:
    if not query:
        return ""
    try:
        from utils.memory_db import memory_db
    except Exception as e:
        print(f"[memory] memory_db unavailable: {e}")
        return ""
    try:
        facts = memory_db.search_facts(query, k=k)
        return facts or ""
    except Exception as e:
        print(f"[memory] retrieval failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# LLM init
# ---------------------------------------------------------------------------

def _get_env_first(*names, default=""):
    """
    Look up the first set env var among `names`. This exists because env
    vars starting with a digit (e.g. 9ROUTER_API_KEY) are invalid/rejected
    by some shells and .env loaders. We keep reading the legacy name for
    backward compatibility but prefer a valid identifier if present.
    """
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return default


def init_llm():
    ninerouter_key = _get_env_first("NINEROUTER_API_KEY", "9ROUTER_API_KEY")
    ninerouter_url = _get_env_first(
        "NINEROUTER_URL", "9ROUTER_URL", default="https://9router.com/api/v1/chat/completions"
    )
    base_url = ninerouter_url.replace("/chat/completions", "")
    ninerouter_model = _get_env_first("NINEROUTER_MODEL", "9ROUTER_MODEL", default="google/gemini-pro")
    groq_key = os.getenv("GROQ_API_KEY", "")

    if ninerouter_key:
        llm = ChatOpenAI(
            api_key=ninerouter_key,
            base_url=base_url,
            model=ninerouter_model,
            temperature=0.4,
            timeout=30,
            max_retries=1,
        )
        if groq_key:
            groq_llm = ChatGroq(
                api_key=groq_key,
                model_name="llama-3.3-70b-versatile",
                temperature=0.4,
                timeout=30,
                max_retries=1,
            )
            llm = llm.with_fallbacks([groq_llm])
        return llm

    if groq_key:
        return ChatGroq(
            api_key=groq_key,
            model_name="llama-3.3-70b-versatile",
            temperature=0.4,
            timeout=30,
            max_retries=1,
        )

    raise ValueError(
        "No LLM API keys configured (NINEROUTER_API_KEY/9ROUTER_API_KEY or GROQ_API_KEY)."
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
# NOTE: removed the stray line claiming a "coder_skill" tool auto-activates
# new skills next session - that tool doesn't exist in this graph. New
# skill files just get picked up by load_all_tools() on its next call
# (immediately now, thanks to the mtime-based cache above), same as any
# other tool.
#
# The prompt used to be one giant always-sent block (identity + skill
# authoring rules + FSD/testing workflow, ~40 lines) regardless of whether
# the turn had anything to do with coding at all. That's wasted tokens on
# a plain "halo, gimana progress project X?" turn.
#
# CORE_SYSTEM_PROMPT below is what's always sent - identity, tone, and the
# memory-usage reminder (memory usage is cheap and always relevant). The
# skill-authoring rules and the FSD/testing workflow are split into
# OPTIONAL_PROMPT_BLOCKS: each has a `full` version (all the detail) and a
# `short` version (one-line pointer). build_dynamic_prompt() decides which
# variant to use per turn based on keyword overlap with the user's query -
# same idea as select_relevant_tools, just applied to prompt text instead
# of tool schemas. This is deliberately fail-OPEN toward `full`: if we're
# not sure a turn is dev-related, we'd rather over-include than risk the
# agent silently ignoring a rule (e.g. writing an HTML draft without
# Tailwind, or forgetting to write a unit test) because the reminder got
# compressed away on the wrong turn.

CORE_SYSTEM_PROMPT = """You are a highly capable AI assistant running on the user's desktop.
You have access to several tools. Use them to help the user.
You have long-term memory (a Notebook). Automatically save important information using the 'remember_fact' tool: user personal facts, project context/architecture, dependencies used, and especially past BUGS/ERRORS from your code so they are never repeated.
If memory becomes outdated (e.g. project deleted), use 'forget_fact' to remove it.
If you face a coding problem or need context, use the 'recall_facts' tool to search your past solutions.
If a tool returns an error, read it carefully and try again to fix the problem.
IMPORTANT (Token efficiency): When you need multiple pieces of data at once, call multiple tools IN PARALLEL in a single response. Never call them one-by-one sequentially.
Do not stop until you have either succeeded or fundamentally cannot proceed.
PENTING: Gunakan bahasa Indonesia yang SANGAT SANTAI, ramah, dan luwes layaknya sedang ngobrol dengan teman (contoh: pakai kata 'aku', 'kamu', 'nih'). JANGAN PERNAH memberikan jawaban berupa poin-poin kaku tanpa basa-basi. HARAM HUKUMNYA membalas dengan kalimat pendek-pendek seperti robot (contoh buruk: "Pilih satu. Buat. Selesai."). Bumbui setiap responmu dengan interaksi manusiawi dan asyik!"""

OPTIONAL_PROMPT_BLOCKS = {
    "skill_authoring": {
        "keywords": {
            "tool", "skill", "fitur", "fungsi", "integrasi", "otomatis",
            "bikin", "buat", "extend", "tambahin", "plugin",
        },
        "full": """[SKILL AUTHORING RULES]
If you need a capability you don't have, you may write a new Python skill. RULES:
1. Save ALL new skill files ONLY inside `skills/generated/`. NEVER create Python files in the project root.
2. MANDATORY: Every function exposed as a tool MUST use the `@tool` decorator from `langchain_core.tools`. Without `@tool` it will never be discovered. Minimal template:
```python
from langchain_core.tools import tool

@tool
def my_tool(param1: str, param2: int = 10) -> str:
    \"\"\"Clear description — the LLM reads this to decide when to call the tool.\"\"\"
    # implementation
    return "result"
```
3. Build DYNAMIC, reusable tools with parameters — never hardcode a single task (e.g. `search_files(query, limit)` not `check_email_today()`).
4. Temporary/scratch scripts go in `scratch/` (create it if missing). NEVER put temp files in the root.
5. ANTI-DUPLICATION: Before creating a new project folder, check `projects/` for an existing one. Save new projects to long-term memory via `remember_fact`.
6. Skills saved to `skills/generated/` are auto-reloaded on the next tool call — no special activation needed. If loading fails with 'Skipping... No @tool-decorated function found', add the missing `@tool` decorator.""",
        "short": "[Skills] New tool → save ONLY in `skills/generated/`, MUST use @tool decorator, make it dynamic/reusable, scratch files → `scratch/`, check `projects/` before creating a new folder.",
    },
    "fsd_workflow": {
        "keywords": {
            "kode", "coding", "fitur", "bug", "implementasi", "deploy",
            "backend", "frontend", "api", "task", "tasks", "fsd", "test",
            "testing", "error", "endpoint", "ui", "desain",
            "project", "proyek", "schema", "skema", "struktur"
        },
        "full": """[CODING WORKFLOW — STRICTLY ENFORCED]
Follow this exact sequence. Skipping steps is FORBIDDEN:
1. DISCUSS & FSD: If the user is exploring an idea, DO NOT create folders, generate code, or write any files. Collaborate to produce a textual FSD until the user explicitly agrees.
2. JSON SCHEMA: After FSD approval, design the project structure as a JSON schema (models, relations, routes, controllers). Write it to a .json file. STOP HERE and ask the user to review before continuing.
3. GENERATE CODE: Only after the user explicitly approves the schema, run `generate_project_from_schema` (set output_dir to the `backend` folder, NOT `app`). NEVER run this tool without schema approval.
4. CUSTOM LOGIC: Only write/edit code manually for specific logic that the generator cannot handle.
5. FRONTEND: UI must use TailwindCSS CDN with a premium design.
6. UNIT TESTS: Every custom function must have tests (pytest / Pest / Jest).
7. DOCS: Record bugs and solutions in memory via `remember_fact`.""",
        "short": "[Workflow] 1. Discuss (no files/code), 2. FSD, 3. Write schema.json then STOP and await user approval, 4. Run `generate_project_from_schema` ONLY after approval. NEVER run codegen before schema is reviewed.",
    },
    "schema_guidelines": {
        "keywords": {
            "schema", "skema", "model", "struktur", "database", "tabel"
        },
        "full": """[JSON SCHEMA FORMAT RULES]
When generating an app schema, the output MUST follow this structure exactly:
1. `models`: Table definitions. Required fields: `name`, `table`, `columns` (array of objects with `name`, `type`, etc. — NOT `fields`), `relations` (array with `type`, `model`, `foreign_key`).
2. `routes`: Array of objects. Required: `path`, `method` (e.g. 'get', 'post'), `controller` (object: `{"name": "ControllerName", "function": "functionName"}`).
3. `controllers`: Array of objects. Required: `name`, `model`, `functions` (array of objects with `name` and `ai_inject_logic`). Use `"ai_inject_logic": "standard"` for plain CRUD. For complex logic, describe it in plain English in `ai_inject_logic`.

NAMING CONVENTIONS (follow Laravel/REST standards — English only):
- `models[].name`: PascalCase English. e.g. `Customer`, `Transaction`, `TransactionDetail`
- `models[].table`: plural snake_case English. e.g. `customers`, `transactions`, `transaction_details`
- `routes[].path`: plural kebab-case English. e.g. `/customers`, `/transactions`, `/transaction-details`
- `controllers[].name`: PascalCase + "Controller". e.g. `CustomerController`
NEVER use Indonesian names for tables/routes. Always translate: Pelanggan→Customer, Transaksi→Transaction, Barang→Item, MutasiBarang→StockMutation, Pengeluaran→Expense, Layanan→Service.

CORRECT controller example (NEVER use array of strings for functions):
```json
{
  "name": "CustomerController",
  "model": "Customer",
  "functions": [
    {"name": "index", "ai_inject_logic": "standard"},
    {"name": "store", "ai_inject_logic": "Validate input and save."},
    {"name": "show", "ai_inject_logic": "standard"},
    {"name": "update", "ai_inject_logic": "standard"},
    {"name": "destroy", "ai_inject_logic": "standard"},
    {"name": "exportPdf", "ai_inject_logic": "Generate a PDF of the customer list and return the URL."}
  ]
}
```
The example above is illustrative — add any custom endpoints the app needs beyond basic CRUD.
NEVER omit `routes` or `controllers`. The controller object in routes must always be `{"name": "...", "function": "..."}`.""",
        "short": "[Schema] Output must include `models`, `routes`, `controllers`. Use English plural names for table/path (e.g. `customers`, `transactions`). Controller functions must be array-of-objects with `name` + `ai_inject_logic`, never array-of-strings.",
    },
}




def build_dynamic_prompt(active_project: str = None, user_query: str = None) -> str:
    """
    Assemble the system prompt from CORE_SYSTEM_PROMPT plus whichever
    optional blocks are relevant to `user_query`. Each optional block
    contributes its `full` text if the query's keywords overlap the
    block's trigger set (or if user_query is empty/unknown - fail open),
    otherwise its `short` one-liner so the rule is never fully dropped,
    just compressed.

    The FSD workflow block is additionally forced to `full` the first
    time a project is worked on (no tasks.md yet), since that's exactly
    the phase where those steps matter most and there's no prior context
    to fall back on.
    """
    prompt = CORE_SYSTEM_PROMPT
    tokens = _tokenize(user_query or "")

    skill_block = OPTIONAL_PROMPT_BLOCKS["skill_authoring"]
    use_full = (not user_query) or bool(tokens & skill_block["keywords"])
    prompt += "\n\n" + (skill_block["full"] if use_full else skill_block["short"])

    schema_block = OPTIONAL_PROMPT_BLOCKS["schema_guidelines"]
    use_full = (not user_query) or bool(tokens & schema_block["keywords"])
    prompt += "\n\n" + (schema_block["full"] if use_full else schema_block["short"])

    if active_project:
        prompt += f"\n\n[KONTEKS PROYEK AKTIF]\nKamu sedang bekerja pada proyek: {active_project}\n"
        prompt += f"Semua file/kode untuk proyek ini WAJIB diletakkan di dalam folder `projects/{active_project}/`.\n"
        prompt += "JANGAN menaruh kode aplikasi di folder `skills/`!\n"

        fsd_block = OPTIONAL_PROMPT_BLOCKS["fsd_workflow"]
        tasks_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "projects", active_project, "tasks.md"
        )
        no_tasks_yet = not os.path.exists(tasks_path)
        use_full = (not user_query) or no_tasks_yet or bool(tokens & fsd_block["keywords"])
        prompt += "\n\n" + (fsd_block["full"] if use_full else fsd_block["short"])

    return prompt


# ---------------------------------------------------------------------------
# Logging callback
# ---------------------------------------------------------------------------

class AgentLoggingCallback(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        """Called when any LLM (including ChatModels) finishes generating."""
        try:
            # Extract token usage - try multiple locations
            usage = None

            # 1. Standard LangChain location (ChatOpenAI, ChatGroq, etc.)
            if response.llm_output and "token_usage" in response.llm_output:
                usage = response.llm_output["token_usage"]

            # 2. Some providers put it directly in generation_info
            if not usage and response.generations:
                gen = response.generations[0][0]
                gen_info = getattr(gen, "generation_info", None) or {}
                if "usage" in gen_info:
                    raw = gen_info["usage"]
                    usage = {
                        "prompt_tokens": raw.get("prompt_tokens", 0),
                        "completion_tokens": raw.get("completion_tokens", 0),
                        "total_tokens": raw.get("total_tokens", 0),
                    }

                # 3. usage_metadata on the message (newer LangChain ChatGeneration)
                if not usage:
                    message = getattr(gen, "message", None)
                    meta = getattr(message, "usage_metadata", None) if message else None
                    if meta:
                        usage = {
                            "prompt_tokens": getattr(meta, "input_tokens", 0),
                            "completion_tokens": getattr(meta, "output_tokens", 0),
                            "total_tokens": getattr(meta, "total_tokens", 0),
                        }

            if usage:
                prompt_tokens = usage.get("prompt_tokens", 0)
                comp_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)
                print(f"\n🪙 [Token Usage] Prompt: {prompt_tokens} | Completion: {comp_tokens} | Total: {total_tokens}")
                log_token_usage(usage)
            else:
                # Debug: show raw structure so we can trace the right location
                print(f"\n⚠️ [Token Usage] Not found. llm_output keys: {list((response.llm_output or {}).keys())}")

            # Log LLM response content
            if response.generations:
                gen = response.generations[0][0]
                message = getattr(gen, "message", None)
                content = getattr(message, "content", getattr(gen, "text", ""))
                tool_calls = getattr(message, "tool_calls", []) if message else []
                log_internal_step("llm_response", {
                    "content": content,
                    "tool_calls": tool_calls
                })
        except Exception as e:
            print(f"[Callback Error] on_llm_end: {e}")

    def on_tool_start(self, serialized, input_str, **kwargs):
        try:
            tool_name = serialized.get("name", "unknown")
            args = json.loads(input_str) if isinstance(input_str, str) else input_str
            log_internal_step("tool_start", {"tool_name": tool_name, "args": args})
        except Exception:
            pass

    def on_tool_end(self, output, **kwargs):
        try:
            log_internal_step("tool_end", {"output": str(output)[:1000]})
        except Exception:
            pass


global_callbacks = [AgentLoggingCallback()]

# ---------------------------------------------------------------------------
# Agent executor factory
# ---------------------------------------------------------------------------

def get_agent_executor(active_project: str = None, user_query: str = None):
    """
    Creates and returns a new agent executor with dynamically loaded tools.
    Tools are cached across calls (see load_all_tools) and only re-imported
    when a skill file on disk has actually changed, so calling this every
    turn stays cheap.

    `user_query` is optional - pass the latest user message content (e.g.
    `messages[-1].content`) to enable:
      - keyword-based tool filtering, once the tool count is large enough
        for that to matter (see select_relevant_tools / TOOL_FILTER_THRESHOLD)
      - automatic long-term memory retrieval, injected into the system
        prompt as [INGATAN MASA LALU] (see retrieve_memories)
      - dynamic system prompt sizing: the skill-authoring and FSD-workflow
        instruction blocks only get sent in full when the query looks
        dev-related, otherwise a one-line compressed reminder is sent
        instead (see build_dynamic_prompt)
    If omitted, all three fall back to their safest/most complete behavior:
    all tools get bound, no auto memory injection (agent can still use
    `recall_facts` manually), and the full prompt blocks are always sent.
    """
    current_tools = load_all_tools()
    if user_query:
        current_tools = select_relevant_tools(current_tools, user_query)

    current_llm = init_llm()

    final_prompt = build_dynamic_prompt(active_project=active_project, user_query=user_query)

    memories = retrieve_memories(user_query) if user_query else ""
    if memories:
        final_prompt += f"\n\n[INGATAN MASA LALU (ChromaDB)]\n{memories}\n"

    return create_react_agent(
        model=current_llm.with_config(callbacks=global_callbacks),
        tools=current_tools,
        prompt=SystemMessage(content=final_prompt),
    )
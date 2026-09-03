import os
import ast
from langchain_core.tools import BaseTool
import importlib
import inspect
import functools
from core.dynamic_prompt import _tokenize
# ---------------------------------------------------------------------------
# Tool loading (with mtime-based caching + hot-reload + pre-import validation)
# ---------------------------------------------------------------------------

_BASE_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
_GENERATED_SKILLS_DIR = os.path.join(_BASE_SKILLS_DIR, "generated")
# ---------------------------------------------------------------------------
# Tool output size limiter (Opsi C)
# ---------------------------------------------------------------------------
# If a tool returns more than TOOL_OUTPUT_THRESHOLD chars, we save the full
# output to a timestamped file and return only a short summary to the LLM.
# This prevents huge HTML/JSON/log dumps from bloating the context window.

TOOL_OUTPUT_THRESHOLD = 1500  # chars - tune as needed
_LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

# Only bother filtering once the tool count gets large enough that context
# bloat is a real concern. Below this, just bind everything - filtering has
# no benefit and only risks accidentally hiding a tool the agent needed.
TOOL_FILTER_THRESHOLD = 15
MAX_RELEVANT_TOOLS = 12

# Tools that must always be available regardless of the query - the agent's
# core capabilities (memory, guideline lookup) shouldn't ever get filtered
# out just because the wording of the query didn't happen to match them.
CORE_TOOL_NAMES = {"remember_fact", "recall_facts", "forget_fact","read_file"}

# Cache: {file_path: mtime} so we only re-import files that actually changed,
# instead of blindly importlib.import_module-ing (and never reloading) or
# reloading everything every single turn (v1's problem).
_tool_cache = {
    "tools": [],       # list[BaseTool]
    "file_mtimes": {},  # path -> last seen mtime
}

def _get_decorator_name(dec: ast.expr) -> str:
    """
    Resolve the name of a decorator node, handling both bare decorators
    (@tool, @module.tool) and call-style decorators with arguments
    (@tool(name="..."), @module.tool(return_direct=True)).

    FIX: the previous version only handled ast.Name / ast.Attribute and
    fell through to "" for ast.Call, which meant any @tool(...) with
    arguments was silently invisible to the validator - a perfectly
    valid generated skill would get rejected with "No @tool-decorated
    function found."
    """
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""

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

    # Require at least one function decorated with @tool (bare or with
    # arguments) - otherwise it's not going to register as a BaseTool
    # anyway, so no point importing it.
    has_tool_decorator = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if _get_decorator_name(dec) == "tool":
                    has_tool_decorator = True

    if not has_tool_decorator:
        return False, "No @tool-decorated function found - refusing to import."

    return True, "ok"


def _wrap_tool_output(tool: BaseTool) -> BaseTool:
    """
    Wraps a BaseTool so that if its string output exceeds TOOL_OUTPUT_THRESHOLD,
    the full output is saved to a file and a compact summary is returned instead.
    The LLM only sees the summary + file path, keeping context window small.

    FIX (vs previous version):
    - Uses object.__setattr__ instead of plain attribute assignment, since
      BaseTool is a pydantic model and direct assignment to a non-field
      attribute can raise under some pydantic v2 configs.
    - CRITICAL: uses @functools.wraps(original_run) on both wrappers.
      LangChain does NOT always pass `config`/`run_manager` blindly - it
      inspects the callable's signature at call time (inspect.signature)
      to decide whether the tool's _run/_arun accepts those params, and
      only injects them if it sees them declared. A wrapper written as
      plain `def _run_with_limit(*args, **kwargs)` hides those parameter
      names from that inspection, so LangChain silently stops passing
      `config` - but the REAL underlying _run (e.g. StructuredTool._run)
      still requires `config` as a mandatory keyword-only argument,
      causing: "StructuredTool._run() missing 1 required keyword-only
      argument: 'config'". functools.wraps sets __wrapped__, which
      inspect.signature() follows by default, so LangChain sees the
      original signature and keeps injecting config/run_manager
      correctly - while the wrapper body itself stays generic and just
      forwards whatever it receives.
    - Also wraps _arun (if the tool defines a custom async implementation),
      so large outputs from async tools get truncated too. Tools that don't
      override _arun (i.e. they fall back to running _run in a thread) are
      already covered by the _run wrap above.
    """
    original_run = tool._run
    original_arun = getattr(tool, "_arun", None)

    def _limit(result_str: str) -> str:
        if len(result_str) <= TOOL_OUTPUT_THRESHOLD:
            return result_str
        from datetime import datetime
        tool_log_dir = os.path.join(_LOGS_DIR, tool.name)
        os.makedirs(tool_log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = f"{ts}.txt"
        fpath = os.path.join(tool_log_dir, fname)
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(result_str)
        except Exception:
            return result_str  # fallback: return as-is if save fails
        preview = result_str[:300].replace("\n", " ")
        rel_path = f"logs/{tool.name}/{fname}"
        return (
            f"[Output terlalu panjang: {len(result_str):,} chars]\n"
            f"✅ Sudah disimpan ke: {rel_path}\n"
            f"Preview (300 chars pertama):\n{preview}..."
        )

    @functools.wraps(original_run)
    def _run_with_limit(*args, **kwargs):
        result = original_run(*args, **kwargs)
        result_str = str(result) if not isinstance(result, str) else result
        return _limit(result_str)

    object.__setattr__(tool, "_run", _run_with_limit)

    if original_arun is not None:
        @functools.wraps(original_arun)
        async def _arun_with_limit(*args, **kwargs):
            result = await original_arun(*args, **kwargs)
            result_str = str(result) if not isinstance(result, str) else result
            return _limit(result_str)

        object.__setattr__(tool, "_arun", _arun_with_limit)

    return tool

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
    print(f"[TOOLS] Selected: {result}")
    return result

def load_all_tools(force: bool = False):
    """
    Scan skills/ and skills/generated/ for *_skill.py files, validate them,
    import (or re-import if changed) them, and collect any BaseTool
    instances defined inside.

    - actually reloads a module if the underlying file changed (mtime),
      so edits to a previously-broken generated skill take effect
      without restarting the process.
    - validates the file with ast.parse before importing it, so a
      malformed/unsafe-looking generated file doesn't get silently
      imported (and doesn't crash the whole tool-loading pass).
    - is cheap to call every turn: if nothing changed on disk, it
      returns the cached tool list instead of re-scanning imports.

    FIX (vs previous version): files that fail validation or fail to
    import now still get their mtime recorded in the cache. Previously
    a broken file's mtime was never cached, which meant the "did
    anything change?" check compared None vs its real mtime on every
    single call and returned True forever - silently forcing a full
    re-scan/re-import of ALL skill files on every turn for as long as
    that one broken file existed, defeating the whole point of the
    mtime cache. Now a broken file is only retried when it's actually
    edited again (its mtime changes).
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
            new_mtimes[file_path] = mtime  # cache even on failure - avoid retry-every-turn
            continue

        try:
            if module_name in importlib.sys.modules:
                module = importlib.reload(importlib.sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
        except Exception as e:
            print(f"[skills] Warning: failed to load {module_name}: {e}")
            new_mtimes[file_path] = mtime  # same - only retry once the file is edited again
            continue

        for _, obj in inspect.getmembers(module):
            if isinstance(obj, BaseTool) and obj.name not in [t.name for t in dynamic_tools]:
                dynamic_tools.append(_wrap_tool_output(obj))

        new_mtimes[file_path] = mtime

    _tool_cache["tools"] = dynamic_tools
    _tool_cache["file_mtimes"] = new_mtimes
    return dynamic_tools

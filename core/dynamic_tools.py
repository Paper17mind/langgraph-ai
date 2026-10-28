import os
import ast
import re
from langchain_core.tools import BaseTool
import importlib
import inspect
import functools
from core.dynamic_prompt import _tokenize

_BASE_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
_GENERATED_SKILLS_DIR = os.path.join(_BASE_SKILLS_DIR, "generated")
_LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
TOOL_OUTPUT_THRESHOLD = 1500

# Cache: {file_path: mtime}
_tool_cache = {
    "tools": [],       # list[BaseTool]
    "file_mtimes": {},  # path -> last seen mtime
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. CORE TOOLS: Selalu tersedia di setiap percakapan
# ─────────────────────────────────────────────────────────────────────────────
CORE_TOOL_NAMES = {
    "remember_fact", "recall_facts", "forget_fact",
    "read_file", "register_project", "audit_project", "list_registered_projects"
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. DOMAIN INTENTS: Menghubungkan sinonim / niat user ke kumpulan tools terkait
# ─────────────────────────────────────────────────────────────────────────────
DOMAIN_KEYWORDS = {
    "maintainer": {
        "keywords": {"audit", "cve", "vulnerability", "maintainer", "project", "rentan", "keamanan", "scan", "bug", "dep", "dependency", "patch"},
        "tools": {"register_project", "list_registered_projects", "audit_project", "audit_dependencies", "audit_web_security", "scan_local_code_security", "read_file", "write_code_to_file"}
    },
    "coding": {
        "keywords": {"code", "coding", "buatkan", "tulis", "file", "edit", "bikin", "fungsi", "function", "class", "script", "program", "baris", "line"},
        "tools": {"write_code_to_file", "read_file", "read_specific_line", "write_specific_line", "search_in_file", "init_project", "save_fsd_document", "execute_system_command"}
    },
    "codegen": {
        "keywords": {"schema", "codegen", "scaffold", "generate", "framework", "express", "laravel", "fastapi", "model", "controller", "route"},
        "tools": {"validate_project_schema", "scaffold_project_from_schema", "get_codegen_queue_status", "read_file", "write_code_to_file"}
    },
    "osint": {
        "keywords": {"ip", "whois", "dns", "domain", "subdomain", "email", "breach", "kebocoran", "username", "footprint", "exif", "wayback", "snapshot", "osint"},
        "tools": {"lookup_whois_info", "lookup_ip_info", "lookup_dns_records", "lookup_subdomains", "check_email_breach", "scan_email_platforms", "search_username_footprint", "check_wayback_snapshots", "extract_image_exif"}
    },
    "web": {
        "keywords": {"search", "cari", "googling", "duckduckgo", "browsing", "url", "link", "web", "fetch", "crawl", "scrape", "scraping", "baca web"},
        "tools": {"search_duckduckgo", "fetch_url_content", "crawl"}
    },
    "system": {
        "keywords": {"terminal", "bash", "shell", "command", "cmd", "exec", "eksekusi", "jalankan", "pip", "schedule", "jadwal", "ingatkan", "alarm", "token", "usage"},
        "tools": {"execute_system_command", "schedule_task", "get_token_usage_stats"}
    },
    "multimedia": {
        "keywords": {"gambar", "image", "foto", "youtube", "transkrip", "transcript", "video", "visual"},
        "tools": {"generate_image_tool", "analyze_image_tool", "get_youtube_transcript"}
    }
}


def _get_decorator_name(dec: ast.expr) -> str:
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _validate_skill_source(file_path: str) -> tuple[bool, str]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        return False, f"Could not read file: {e}"

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"

    has_tool = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                name = _get_decorator_name(dec)
                if name == "tool":
                    has_tool = True
                    break
        if has_tool:
            break

    if not has_tool:
        return False, "No @tool-decorated function found."

    return True, "ok"


def _wrap_tool_output(tool: BaseTool) -> BaseTool:
    orig_func = tool.func
    orig_coroutine = tool.coroutine

    def _truncate_and_save(result: str, tool_name: str) -> str:
        if len(result) <= TOOL_OUTPUT_THRESHOLD:
            return result

        os.makedirs(_LOGS_DIR, exist_ok=True)
        import time
        ts = int(time.time() * 1000)
        filename = f"{tool_name}_{ts}.log"
        file_path = os.path.join(_LOGS_DIR, filename)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(result)
        except Exception as e:
            return result[:TOOL_OUTPUT_THRESHOLD] + f"\n\n[Warning: failed to save full log: {e}]"

        head = result[:800]
        tail = result[-400:]
        total_len = len(result)

        return (
            f"[Output terlalu panjang: {total_len} karakter. "
            f"Sudah disimpan ke: {file_path}]\n\n"
            f"--- Potongan Awal ---\n{head}\n\n"
            f"--- Potongan Akhir ---\n{tail}\n\n"
            f"[Gunakan tool read_file dengan path di atas jika butuh membaca seluruh output]"
        )

    if orig_func:
        @functools.wraps(orig_func)
        def sync_wrapper(*args, **kwargs):
            res = orig_func(*args, **kwargs)
            return _truncate_and_save(str(res), tool.name)
        tool.func = sync_wrapper

    if orig_coroutine:
        @functools.wraps(orig_coroutine)
        async def async_wrapper(*args, **kwargs):
            res = await orig_coroutine(*args, **kwargs)
            return _truncate_and_save(str(res), tool.name)
        tool.coroutine = async_wrapper

    return tool


def select_relevant_tools(all_tools: list, query: str) -> list:
    """
    Pilih tools secara cerdas & fail-safe:
    1. Selalu sertakan CORE_TOOL_NAMES (memory, project registry, read_file).
    2. Deteksi Domain Intent dari query (Maintainer, Coding, Codegen, OSINT, Web, System, Multimedia).
    3. Jika domain cocok, sertakan tools domain tersebut.
    4. Keyword overlap scoring sebagai layer kedua untuk tools yang tidak masuk domain mapping.
    5. FAIL-OPEN: Jika query umum atau hasil filter kosong, kembalikan SEMUA tools agar tidak ada tool yang hilang.
    """
    if not all_tools or not query:
        return all_tools

    query_lower = query.lower()
    query_tokens = _tokenize(query)

    # 1. Start with Core Tools
    selected_names = set(CORE_TOOL_NAMES)

    # 2. Match Domain Intent
    matched_domains = False
    for domain, config in DOMAIN_KEYWORDS.items():
        if config["keywords"] & query_tokens or any(kw in query_lower for kw in config["keywords"]):
            selected_names.update(config["tools"])
            matched_domains = True

    # 3. Direct Tool Name Matching (jika user menyebut nama tool atau bagian namanya)
    for t in all_tools:
        clean_name = t.name.lower().replace("_", " ")
        if clean_name in query_lower or t.name.lower() in query_lower:
            selected_names.add(t.name)

    # 4. Keyword Overlap Scoring fallback
    for t in all_tools:
        if t.name in selected_names:
            continue
        tool_tokens = _tokenize(t.name) | _tokenize(t.description or "")
        if len(query_tokens & tool_tokens) >= 2:
            selected_names.add(t.name)

    # 5. Fail-Safe: Jika tidak ada domain yang cocok (misal query santai / ambigu),
    # atau tools yang terpilih terlalu sedikit padahal user minta sesuatu, FAIL-OPEN (return all).
    if not matched_domains and len(selected_names) <= len(CORE_TOOL_NAMES):
        return all_tools

    # Filter tool objects
    tool_map = {t.name: t for t in all_tools}
    result = [tool_map[name] for name in selected_names if name in tool_map]

    # Pastikan jika filter menghasilkan list kosong (kasus ekstrem), kembalikan all_tools
    return result if result else all_tools


def load_all_tools(force: bool = False):
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

    if set(_tool_cache["file_mtimes"].keys()) - set(current_files.keys()):
        changed = True

    if not changed and _tool_cache["tools"]:
        return _tool_cache["tools"]

    dynamic_tools = []
    new_mtimes = {}

    for file_path, (mtime, module_prefix, filename) in current_files.items():
        module_name = f"{module_prefix}.{filename[:-3]}"

        ok, reason = _validate_skill_source(file_path)
        if not ok:
            print(f"[skills] Skipping {module_name}: {reason}")
            new_mtimes[file_path] = mtime
            continue

        try:
            if module_name in importlib.sys.modules:
                module = importlib.reload(importlib.sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)
        except Exception as e:
            print(f"[skills] Warning: failed to load {module_name}: {e}")
            new_mtimes[file_path] = mtime
            continue

        for _, obj in inspect.getmembers(module):
            if isinstance(obj, BaseTool) and obj.name not in [t.name for t in dynamic_tools]:
                dynamic_tools.append(_wrap_tool_output(obj))

        new_mtimes[file_path] = mtime

    _tool_cache["tools"] = dynamic_tools
    _tool_cache["file_mtimes"] = new_mtimes
    return dynamic_tools

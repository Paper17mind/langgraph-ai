"""
Schema-driven code generator — main @tool entry points.

Tools:
  - read_project_schema     : Read and summarize a project schema JSON file
  - generate_project_from_schema : Phase 1 (instant) + Phase 2 (background queue)
"""
import json
import os
from langchain_core.tools import tool
from skills.generated.codegen import ADAPTERS
from skills.generated.codegen.ai_inject_worker import queue_jobs, start_worker_thread


def _resolve_path(path: str) -> str:
    """Resolve path relative to the project root if not absolute."""
    if os.path.isabs(path):
        return path
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, path)


def _load_schema(schema_path: str) -> dict:
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_files(files: dict[str, str], output_dir: str) -> list[str]:
    """Write {relative_path: content} to disk. Returns list of written paths."""
    written = []
    for rel_path, content in files.items():
        full_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(rel_path)
    return written


@tool
def read_project_schema(schema_path: str) -> str:
    """Read and summarize project JSON schema."""
    try:
        path = _resolve_path(schema_path)
        schema = _load_schema(path)

        models = schema.get("models", [])
        routes = schema.get("routes", [])
        controllers = schema.get("controllers", [])

        model_list = "\n".join(
            f"  - {m['name']} ({m['table']}, {len(m.get('columns',[]))} cols, "
            f"{len(m.get('relations',[]))} relations)"
            for m in models
        )

        ai_jobs = []
        std_fns = []
        for ctrl in controllers:
            for fn in ctrl.get("functions", []):
                if fn.get("ai_inject_logic"):
                    ai_jobs.append(f"  - {ctrl['name']}.{fn['name']}: {fn['ai_inject_logic']}")
                else:
                    std_fns.append(f"  - {ctrl['name']}.{fn['name']}")

        return (
            f"📋 **Schema Summary: {os.path.basename(path)}**\n\n"
            f"**Models ({len(models)}):**\n{model_list}\n\n"
            f"**Routes:** {len(routes)} total\n\n"
            f"**Phase 1 — Deterministic functions ({len(std_fns)}):**\n"
            + ("\n".join(std_fns) or "  (none)") +
            f"\n\n**Phase 2 — ai_inject_logic jobs ({len(ai_jobs)}):**\n"
            + ("\n".join(ai_jobs) or "  (none)")
        )
    except FileNotFoundError:
        return f"❌ File tidak ditemukan: {schema_path}"
    except json.JSONDecodeError as e:
        return f"❌ JSON tidak valid: {e}"
    except Exception as e:
        return f"❌ Error membaca schema: {e}"


@tool
def generate_project_from_schema(
    schema_path: str,
    framework: str,
    output_dir: str,
    ai_delay_seconds: int = 3,
) -> str:
    """Generate Express/Laravel/FastAPI project from JSON schema."""
    try:
        schema_path = _resolve_path(schema_path)
        output_dir = _resolve_path(output_dir)

        if not os.path.exists(schema_path):
            return f"❌ Schema file tidak ditemukan: {schema_path}"

        framework = framework.lower().strip()
        if framework not in ADAPTERS:
            return f"❌ Framework tidak didukung: '{framework}'. Pilihan: {list(ADAPTERS.keys())}"

        schema = _load_schema(schema_path)
        adapter = ADAPTERS[framework](schema, output_dir)

        # ---------------------------------------------------------------
        # Phase 1 — Synchronous, no LLM
        # ---------------------------------------------------------------
        all_written = []

        print(f"[codegen] Phase 1: generating {framework} project...")
        all_written += _write_files(adapter.generate_models(), output_dir)
        all_written += _write_files(adapter.generate_migrations(), output_dir)
        all_written += _write_files(adapter.generate_routes(), output_dir)
        all_written += _write_files(adapter.generate_controllers(), output_dir)
        all_written += _write_files(adapter.generate_tests_phase1(), output_dir)

        # ---------------------------------------------------------------
        # Generate Frontend
        # ---------------------------------------------------------------
        print(f"[codegen] Generating frontend html files...")
        frontend_adapter = ADAPTERS["frontend_html"](schema, output_dir)
        all_written += _write_files(frontend_adapter.generate_all(), output_dir)

        phase1_count = len(all_written)

        # ---------------------------------------------------------------
        # Phase 2 — Queue ai_inject_logic jobs
        # ---------------------------------------------------------------
        jobs = adapter.get_ai_inject_jobs()
        queued = queue_jobs(schema_path, framework, output_dir, jobs)

        summary_files = "\n".join(f"  ✅ {f}" for f in all_written[:20])
        if len(all_written) > 20:
            summary_files += f"\n  ... dan {len(all_written)-20} file lainnya"

        result = (
            f"🏗️ **Codegen selesai — {framework.title()}**\n\n"
            f"📁 Output: `{output_dir}`\n\n"
            f"**Phase 1 selesai** ({phase1_count} file):\n{summary_files}\n\n"
        )

        if queued > 0:
            result += (
                f"**Phase 2 dimulai** ({queued} ai_inject_logic jobs):\n"
                f"  Delay: {ai_delay_seconds}s antar job\n"
                f"  Estimasi selesai: ~{queued * ai_delay_seconds}s\n"
                f"  Kamu akan mendapat notifikasi Telegram setiap job selesai. 🔔"
            )
            start_worker_thread(delay_seconds=ai_delay_seconds)
        else:
            result += "**Phase 2:** Tidak ada ai_inject_logic jobs."

        return result

    except Exception as e:
        import traceback
        return f"❌ Error: {e}\n{traceback.format_exc()[:500]}"

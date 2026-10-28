"""
Codegen capability skill — clean tool interfaces for schema-driven code generation.
"""
import os
import json
from langchain_core.tools import tool
from core.capabilities.codegen.engine import generate_project, ADAPTERS
from core.capabilities.codegen.schema import validate_schema_dict
from core.capabilities.codegen.worker import queue_jobs, start_worker_thread, get_pending_jobs

def _resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, path)

@tool
def validate_project_schema(schema_path: str) -> str:
    """Validate a project schema JSON file structure before code generation."""
    full_path = _resolve_path(schema_path)
    if not os.path.exists(full_path):
        return f"Error: Schema file not found at {full_path}"
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        schema = validate_schema_dict(raw)
        return (
            f"✓ Schema is valid: '{schema['project_name']}'\n"
            f"- Models ({len(schema['models'])}): {', '.join(m.get('name', '') for m in schema['models'])}\n"
            f"- Controllers ({len(schema['controllers'])}): {', '.join(c.get('name', '') for c in schema['controllers'])}\n"
            f"- Routes ({len(schema['routes'])} total)"
        )
    except Exception as e:
        return f"✗ Invalid schema: {e}"

@tool
def scaffold_project_from_schema(
    schema_path: str,
    framework: str = "express",
    output_dir: str = "./generated_project",
    generate_frontend: bool = False,
    run_ai_inject: bool = True,
) -> str:
    """
    Generate Phase 1 scaffold (models, migrations, routes, controllers) from a JSON schema.
    Supported frameworks: express, fastapi, laravel, frontend_html.
    """
    full_path = _resolve_path(schema_path)
    if not os.path.exists(full_path):
        return f"Error: Schema file not found at {full_path}"

    target_dir = _resolve_path(output_dir)

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        res = generate_project(
            schema_data=data,
            framework=framework,
            output_dir=target_dir,
            generate_frontend=generate_frontend,
        )

        files_summary = "\n".join(f"  - {f}" for f in res["written_files"][:15])
        if len(res["written_files"]) > 15:
            files_summary += f"\n  ... and {len(res['written_files']) - 15} more files."

        msg = (
            f"✓ Scaffold successfully generated for '{framework}' at {target_dir}\n"
            f"Files created ({res['total_files']}):\n{files_summary}\n"
        )
        if res["total_ai_jobs"] > 0:
            if run_ai_inject:
                queued = queue_jobs(full_path, framework, target_dir, res["ai_jobs"])
                start_worker_thread(delay_seconds=3)
                msg += f"\nℹ Queued {queued} functions for background AI injection (worker started)."
            else:
                msg += f"\nℹ Note: {res['total_ai_jobs']} functions flagged for AI injection."
        return msg
    except Exception as e:
        return f"✗ Code generation failed: {e}"

@tool
def get_codegen_queue_status() -> str:
    """Check how many AI inject jobs are currently pending in the background worker queue."""
    try:
        pending = get_pending_jobs()
        if not pending:
            return "Codegen worker queue is empty. No pending jobs."
        details = [f"- #{j['id']}: {j['controller']}.{j['function_name']} ({j['framework']})" for j in pending[:10]]
        res = f"Pending codegen jobs ({len(pending)}):\n" + "\n".join(details)
        if len(pending) > 10:
            res += f"\n... and {len(pending) - 10} more."
        return res
    except Exception as e:
        return f"Error checking queue: {e}"

import os
import json
from typing import Dict, Any, List, Tuple
from .schema import validate_schema_dict
from .adapters.express_adapter import ExpressAdapter
from .adapters.fastapi_adapter import FastAPIAdapter
from .adapters.laravel_adapter import LaravelAdapter
from .adapters.frontend_html_adapter import FrontendHtmlAdapter

ADAPTERS = {
    "express": ExpressAdapter,
    "fastapi": FastAPIAdapter,
    "laravel": LaravelAdapter,
    "frontend_html": FrontendHtmlAdapter,
}

def write_files(files: Dict[str, str], output_dir: str) -> List[str]:
    """Write generated {relative_path: content} dict to disk safely."""
    written = []
    for rel_path, content in files.items():
        full_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(rel_path)
    return written

def generate_project(
    schema_data: Dict[str, Any],
    framework: str,
    output_dir: str,
    generate_frontend: bool = False,
) -> Dict[str, Any]:
    """
    Run Phase 1 (deterministic) code generation.
    Returns: {
      "written_files": list[str],
      "ai_jobs": list[dict],
      "framework": str,
      "output_dir": str
    }
    """
    # 1. Validate Schema
    schema_dict = validate_schema_dict(schema_data)
    adapter_cls = ADAPTERS.get(framework.lower())
    if not adapter_cls:
        raise ValueError(f"Unsupported framework '{framework}'. Supported: {list(ADAPTERS.keys())}")

    adapter = adapter_cls(schema_dict, output_dir)
    phase1_files = {}
    if framework.lower() == "frontend_html":
        phase1_files.update(adapter.generate_all())
    else:
        phase1_files.update(adapter.generate_models())
        phase1_files.update(adapter.generate_migrations())
        phase1_files.update(adapter.generate_routes())
        phase1_files.update(adapter.generate_controllers())
        phase1_files.update(adapter.generate_tests_phase1())

    written_files = write_files(phase1_files, output_dir)

    # Optional: generate frontend HTML alongside backend
    if generate_frontend and framework.lower() != "frontend_html":
        frontend_dir = os.path.join(output_dir, "frontend")
        fe_adapter = FrontendHtmlAdapter(schema_dict, frontend_dir)
        fe_files = fe_adapter.generate_all()
        written_files.extend(write_files(fe_files, frontend_dir))

    ai_jobs = adapter.get_ai_inject_jobs()

    return {
        "status": "success",
        "framework": framework,
        "output_dir": output_dir,
        "written_files": written_files,
        "ai_jobs": ai_jobs,
        "total_files": len(written_files),
        "total_ai_jobs": len(ai_jobs),
    }

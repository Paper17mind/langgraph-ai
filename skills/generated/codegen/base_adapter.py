"""
Base adapter interface for schema-driven code generators.
Each framework adapter must inherit this and implement all methods.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """
    Abstract base for framework-specific code generators.

    Schema dict structure:
      {
        "models": [...],
        "routes": [...],
        "controllers": [...]
      }
    """

    def __init__(self, schema: dict, output_dir: str):
        self.schema = schema
        self.output_dir = output_dir
        self.models = {m["name"]: m for m in schema.get("models", [])}
        self.routes = schema.get("routes", [])
        self.controllers = schema.get("controllers", [])

    # ------------------------------------------------------------------
    # Phase 1 — deterministik, no LLM
    # ------------------------------------------------------------------

    @abstractmethod
    def generate_models(self) -> dict[str, str]:
        """Return {relative_path: file_content} for all model files."""
        ...

    @abstractmethod
    def generate_migrations(self) -> dict[str, str]:
        """Return {relative_path: file_content} for migration files."""
        ...

    @abstractmethod
    def generate_routes(self) -> dict[str, str]:
        """Return {relative_path: file_content} for route/router files."""
        ...

    @abstractmethod
    def generate_controllers(self) -> dict[str, str]:
        """
        Return {relative_path: file_content} for controller files.
        Standard action steps are generated here; ai_inject_logic functions
        get a TODO placeholder that Phase 2 will fill in.
        """
        ...

    @abstractmethod
    def generate_tests_phase1(self) -> dict[str, str]:
        """
        Return {relative_path: file_content} for tests derivable from
        the schema without LLM — auth guards, role checks, standard
        action assertions (check_condition → 400, etc.).
        """
        ...

    # ------------------------------------------------------------------
    # Phase 2 helper — called by the background worker
    # ------------------------------------------------------------------

    @abstractmethod
    def build_ai_inject_prompt(
        self,
        controller_name: str,
        function_name: str,
        ai_inject_logic: str,
        model_name: str,
    ) -> str:
        """
        Build a focused LLM prompt that includes only the relevant model
        context (columns + relations) and the ai_inject_logic description.
        Returns the prompt string to send to the LLM.
        """
        ...

    @abstractmethod
    def inject_ai_code(
        self,
        file_path: str,
        function_name: str,
        generated_code: str,
    ) -> None:
        """
        Replace the TODO placeholder in `file_path` for `function_name`
        with the `generated_code` returned by the LLM.
        """
        ...

    # ------------------------------------------------------------------
    # Utility: collect all ai_inject_logic jobs from schema
    # ------------------------------------------------------------------

    def get_ai_inject_jobs(self) -> list[dict[str, Any]]:
        """
        Scan controllers for functions with ai_inject_logic.
        Returns a list of job dicts ready to be queued.
        """
        jobs = []
        for ctrl in self.controllers:
            model_name = ctrl.get("model", "")
            for fn in ctrl.get("functions", []):
                logic = fn.get("ai_inject_logic")
                if logic:
                    if str(logic).lower() == "standard" and "fastapi" not in type(self).__name__.lower():
                        pass # Native support available, skip LLM inject
                    else:
                        jobs.append({
                            "controller": ctrl["name"],
                            "function_name": fn["name"],
                            "ai_inject_logic": logic,
                        "model_name": model_name,
                    })
        return jobs

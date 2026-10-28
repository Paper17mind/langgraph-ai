"""
Standard library schema validator for project codegen.
Zero external dependencies required (works across any python runtime without pydantic).
"""
from typing import Dict, Any, List, Optional

VALID_FRAMEWORKS = {"express", "fastapi", "laravel", "frontend_html"}

class SchemaValidationError(ValueError):
    pass

def validate_schema_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate raw schema dictionary using stdlib.
    Raises SchemaValidationError on invalid structures.
    """
    if not isinstance(raw, dict):
        raise SchemaValidationError("Schema must be a JSON object.")

    project_name = raw.get("project_name", "generated_app")
    models = raw.get("models", [])
    controllers = raw.get("controllers", [])
    routes = raw.get("routes", [])

    if not isinstance(models, list):
        raise SchemaValidationError("'models' must be a list.")
    if not isinstance(controllers, list):
        raise SchemaValidationError("'controllers' must be a list.")
    if not isinstance(routes, list):
        raise SchemaValidationError("'routes' must be a list.")

    model_names = set()
    for m in models:
        if not isinstance(m, dict) or "name" not in m:
            raise SchemaValidationError("Each model must be an object with a 'name' property.")
        model_names.add(m["name"])

    # Validate relation integrity
    for m in models:
        for rel in m.get("relations", []):
            target = rel.get("model")
            if target and target not in model_names:
                raise SchemaValidationError(
                    f"Model '{m['name']}' references non-existent model '{target}' in relations."
                )

    # Validate controller functions
    for ctrl in controllers:
        if not isinstance(ctrl, dict) or "name" not in ctrl:
            raise SchemaValidationError("Each controller must have a 'name'.")

    return {
        "project_name": project_name,
        "models": models,
        "controllers": controllers,
        "routes": routes,
    }

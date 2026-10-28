from .adapters.laravel_adapter import LaravelAdapter
from .adapters.fastapi_adapter import FastAPIAdapter
from .adapters.express_adapter import ExpressAdapter
from .adapters.frontend_html_adapter import FrontendHtmlAdapter
from .schema import validate_schema_dict, SchemaValidationError
from .engine import generate_project

ADAPTERS = {
    "laravel": LaravelAdapter,
    "fastapi": FastAPIAdapter,
    "express": ExpressAdapter,
    "frontend_html": FrontendHtmlAdapter,
}

__all__ = [
    "ADAPTERS",
    "LaravelAdapter",
    "FastAPIAdapter",
    "SchemaValidationError",
    "ExpressAdapter",
    "FrontendHtmlAdapter",
    "validate_schema_dict",
    "generate_project",
]

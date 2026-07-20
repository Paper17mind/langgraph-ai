"""
Codegen adapter package.
Maps framework name → adapter class.
"""
from .laravel_adapter import LaravelAdapter
from .fastapi_adapter import FastAPIAdapter
from .express_adapter import ExpressAdapter
from .frontend_html_adapter import FrontendHtmlAdapter

ADAPTERS = {
    "laravel": LaravelAdapter,
    "fastapi": FastAPIAdapter,
    "express": ExpressAdapter,
    "frontend_html": FrontendHtmlAdapter,
}

__all__ = ["ADAPTERS", "LaravelAdapter", "FastAPIAdapter", "ExpressAdapter", "FrontendHtmlAdapter"]

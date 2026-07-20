"""
Codegen adapter package.
Maps framework name → adapter class.
"""
from .laravel_adapter import LaravelAdapter
from .fastapi_adapter import FastAPIAdapter
from .express_adapter import ExpressAdapter

ADAPTERS = {
    "laravel": LaravelAdapter,
    "fastapi": FastAPIAdapter,
    "express": ExpressAdapter,
}

__all__ = ["ADAPTERS", "LaravelAdapter", "FastAPIAdapter", "ExpressAdapter"]

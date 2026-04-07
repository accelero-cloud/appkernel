from __future__ import annotations


class Config:
    """Dynamic namespace for runtime configuration values."""
    openapi_endpoints: dict = {}


config = Config()

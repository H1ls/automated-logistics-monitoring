# LogistX/onec/__init__.py
"""Public 1C API with lazy imports so pure modules do not require GUI dependencies."""

from typing import TYPE_CHECKING

__all__ = ("OneCBot", "RaceContext")

if TYPE_CHECKING:
    from .bot import OneCBot
    from .context import RaceContext


def __getattr__(name: str):
    if name == "OneCBot":
        from .bot import OneCBot
        return OneCBot
    if name == "RaceContext":
        from .context import RaceContext
        return RaceContext
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

from typing import TYPE_CHECKING

from .shape import ShapeCache

if TYPE_CHECKING:
    from plyunit.backends.integrations import Font, Text

__all__ = ("Font", "ShapeCache", "Text")


def __getattr__(name: str):
    if name not in {"Text", "Font"}:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from plyunit.backends import integrations

    value = getattr(integrations, name)
    globals()[name] = value
    return value

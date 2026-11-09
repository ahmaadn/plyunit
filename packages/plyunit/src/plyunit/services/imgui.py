from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plyunit.backends.imgui import ImGui

__all__ = ("ImGui",)


def __getattr__(name: str):
    if name != "ImGui":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from plyunit.backends.imgui import ImGui

    globals()[name] = ImGui
    return ImGui

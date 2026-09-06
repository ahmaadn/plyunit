"""Optional Dear ImGui integration for plyunit (raylib backend).

Requires the **imgui** extra (imgui-bundle + PyOpenGL; raylib host):
``uv sync --package plyunit --extra raylib --extra imgui`` in the monorepo
workspace.

Immediate-mode usage only — register draw callbacks on ``ImGui``. There is
no scene-graph traversal; ImGui is drawn after all plyunit render passes
via ``ImGui.frame()``, which the user calls from ``App.update`` when
``AppConfig.imgui.enabled`` is True.

The renderer uses imgui_bundle's programmable OpenGL pipeline (bulk VBO
upload), the same approach as ``imp/backend.py`` /
``imp/zengl_renderer.py``.
"""

from __future__ import annotations

try:
    import imgui_bundle  # noqa: F401
    import OpenGL.GL  # noqa: F401
except ImportError as exc:  # pragma: no cover - depends on env
    raise ImportError(
        "plyunit imgui requires imgui-bundle + PyOpenGL: "
        "uv sync --package plyunit --extra raylib --extra imgui"
    ) from exc

from .backend import ImGuiBackend
from .service import ImGui, build_imgui_service

__all__ = [
    "ImGui",
    "ImGuiBackend",
    "build_imgui_service",
]

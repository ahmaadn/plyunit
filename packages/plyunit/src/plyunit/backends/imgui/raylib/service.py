"""ImGui — optional immediate-mode UI service for plyunit.

Lifecycle (controlled via the ``AppConfig.imgui.enabled`` flag):

1. ``init`` builds this service when enabled.
2. ``on_attach`` creates the ImGui context (without hooking App signals —
   ``App`` no longer owns the render pipeline).
3. Each frame, the user calls :meth:`ImGui.frame` from ``App.update(dt)``
   after ``renderer.flush_all(...)`` and before ``window.end_drawing()``:
   NewFrame → user draw panels → Render.
4. ``on_detach`` shuts the backend down.

The UI is **immediate only** — panels are callables registered via
``add_draw`` / ``set_draw``. There is no scene traversal and no render
queue.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from plyunit.core.units.service_unit import ServiceUnit

from .backend import ImGuiBackend

if TYPE_CHECKING:
    from plyunit.core.app import App
    from plyunit.core.schema_config import ImGuiConfig

DrawCallback = Callable[[], None]
"""Type of argument-less callables that draw one ImGui panel."""


class ImGui(ServiceUnit):
    """Optional ImGui service hooked into the App render frame.

    Attributes:
        backend: The active host ImGui backend (input + OpenGL renderer).
        active: ``True`` once the ImGui context is set up and attached to
            the App.
    """

    def __init__(
        self,
        backend: ImGuiBackend | None = None,
        *,
        dark_style: bool = True,
        no_ini: bool = True,
    ) -> None:
        """Initialize the ImGui service.

        Args:
            backend: Host backend. ``None`` = create a default instance.
            dark_style: Apply the dark theme to ImGui.
            no_ini: Disable the ``.ini`` file so ImGui does not persist state.
        """
        super().__init__(name="ImGui", tags={"service", "imgui", "ui"})
        self._backend = backend or ImGuiBackend()
        self._dark_style = dark_style
        self._no_ini = no_ini
        self._draw_callbacks: list[DrawCallback] = []
        self._app: App | None = None
        self._active = False

    @property
    def backend(self) -> ImGuiBackend:
        """The ImGui backend currently in use."""
        return self._backend

    @property
    def active(self) -> bool:
        """``True`` while the service is attached and active."""
        return self._active

    def add_draw(self, callback: DrawCallback) -> None:
        """Register an additional ImGui panel callback (called after NewFrame).

        Args:
            callback: Argument-less callable that draws a panel.
        """
        if callback not in self._draw_callbacks:
            self._draw_callbacks.append(callback)

    def remove_draw(self, callback: DrawCallback) -> None:
        """Remove a registered ImGui panel callback.

        Args:
            callback: Callable to remove (silent no-op if absent).
        """
        try:
            self._draw_callbacks.remove(callback)
        except ValueError:
            return

    def set_draw(self, callback: DrawCallback | None) -> None:
        """Replace the whole callback list with a single callback (or clear it).

        Args:
            callback: A single callback, or ``None`` to empty the list.
        """
        self._draw_callbacks.clear()
        if callback is not None:
            self._draw_callbacks.append(callback)

    def clear_draw(self) -> None:
        """Remove all ImGui panel callbacks."""
        self._draw_callbacks.clear()

    def want_capture_mouse(self) -> bool:
        """Return ``True`` if ImGui wants to capture mouse events.

        Returns:
            The delegated result from the ImGui backend.
        """
        return self._backend.want_capture_mouse()

    def want_capture_keyboard(self) -> bool:
        """Return ``True`` if ImGui wants to capture keyboard events.

        Returns:
            The delegated result from the ImGui backend.
        """
        return self._backend.want_capture_keyboard()

    def on_attach(self, app: App) -> None:
        """Registry hook — set up the ImGui context.

        Args:
            app: The ``App`` instance receiving this service.
        """
        self._app = app
        self._backend.setup(dark_style=self._dark_style, no_ini=self._no_ini)
        self._active = True

    def on_detach(self, app: App) -> None:
        """Detach the service from the ``App`` before the window closes.

        Args:
            app: The ``App`` instance this service is being detached from.
        """
        self._backend.shutdown()
        self._active = False
        self._app = None

    def frame(self, dt: float | None = None) -> None:
        """Run one ImGui frame: NewFrame → draw callbacks → Render.

        Called manually by the user from ``App.update(dt)``, after
        ``renderer.flush_all(...)`` and before ``window.end_drawing()`` so
        ImGui draws on top of the game while still inside the drawing block.

        Args:
            dt: Frame delta time in seconds. ``None`` falls back to
                ``app.window.dt`` (or ``0.0`` when no window is available).
        """
        if not self._active:
            return
        delta = dt
        if delta is None:
            delta = 0.0
            if self._app is not None and self._app.window is not None:
                delta = float(self._app.window.dt)
        self._backend.new_frame(delta)
        for callback in list(self._draw_callbacks):
            callback()
        self._backend.render()


def build_imgui_service(cfg: ImGuiConfig | Any) -> ImGui:
    """Build ``ImGui`` from ``ImGuiConfig`` (composition-root factory)."""
    return ImGui(
        dark_style=bool(cfg.dark_style),
        no_ini=bool(cfg.no_ini),
    )


__all__ = [
    "DrawCallback",
    "ImGui",
    "build_imgui_service",
]

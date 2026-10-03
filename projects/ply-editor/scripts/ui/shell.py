from __future__ import annotations

from typing import TYPE_CHECKING

import plyunit
from scripts.ui.screens.editor_screen import EditorScreen
from scripts.ui.screens.start_screen import StartScreen

if TYPE_CHECKING:
    from app import EditorApp


class EditorShell(plyunit.ServiceUnit):
    """Facade over the engine ``@ImGui`` service.

    The composition root constructs the shell during ``on_load``; the
    attach hook resolves the app context and event bus, registers the
    draw callback, and builds the start and editor screens.
    """

    def __init__(self) -> None:
        super().__init__("EditorShell")

    def on_attach(self, app: EditorApp) -> None:
        """Resolve the engine services and build the editor panels.

        Requires the composition root (``EditorApp.on_load``) to have
        created the context, the event bus, and the project services
        before the shell itself is constructed.
        """
        self.ctx = app.ctx
        self.bus = app.bus

        self._ui = app.ui
        self._ui.add_draw(self.draw)

        self.start_screen = StartScreen()
        self.editor_screen = EditorScreen()
        self._sync_project = False

    @property
    def ui(self) -> plyunit.ImGui:
        """The engine ``ImGui`` service (draw callbacks, capture queries)."""
        return self._ui

    def update(self, dt: float) -> None:
        """Per-frame update hook.

        Reserved seam: input gating against the layout viewport and
        ImGui capture queries belongs here.
        """

        if not self.ctx.workspace.scanning and not self._sync_project:
            self.editor_screen.sync()
            self._sync_project = True

    def draw(self) -> None:
        """Draw one full editor chrome frame."""
        if not self.ctx.project_active and self.ctx.global_.last_project is None:
            self.start_screen.draw()
            self._sync_project = False
            return

        if self._sync_project and self.ctx.project_active:
            self.editor_screen.draw()


__all__ = ["EditorShell"]

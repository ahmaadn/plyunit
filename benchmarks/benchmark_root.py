"""Scene-root submission hooks shared by the bounded benchmark harnesses."""

from collections.abc import Callable

import plyunit as pu


class BenchmarkRoot(pu.NodeUnit):
    """Submit benchmark frames through the canonical node lifecycle."""

    def __init__(self, submit: Callable[[pu.Renderer], None]) -> None:
        """Create a root that delegates frame submission to its harness.

        Args:
            submit: Callback that queues content and records frame metrics.
        """
        super().__init__(name="Root", tags={"root"})
        self._submit = submit

    def render_submit(self, renderer: pu.Renderer, context=None) -> None:
        """Submit one benchmark frame before the renderer flushes.

        Args:
            renderer: Configured renderer receiving this frame's content.
            context: Inherited node state; benchmark passes set state explicitly.
        """
        self._submit(renderer)

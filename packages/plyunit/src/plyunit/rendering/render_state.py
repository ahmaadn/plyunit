"""Render pass configuration, per-item GPU render state, and state interning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from plyunit.core.types import PrColor, RectType, ShaderType
from plyunit.rendering.enum import BlendMode
from plyunit.rendering.render_context import RenderContext

if TYPE_CHECKING:
    from .draw_scope import DrawScope

__all__ = [
    "DEFAULT_RENDER_STATE",
    "RenderContext",
    "RenderPass",
    "RenderState",
    "RenderStateCache",
]


@dataclass
class RenderPass:
    """Configuration for a single render pass.

    Attributes:
        name: Unique pass name used for lookup.
        target: Optional ``RenderTexture`` the pass draws into.
        camera: Optional camera; when None the pass is screen-space.
        clear_color: Optional color for ``clear_background`` before drawing.
        viewport_scissor: Optional (x, y, w, h) rect limiting the draw area.
        order: Pass execution order (ascending).
        min_layer: Minimum layer of items the pass accepts.
        max_layer: Maximum layer of items the pass accepts.
        screen_space: True when the pass uses no camera.
        enabled: Set to False to temporarily disable the pass.
        immediate: Optional immediate callback that overrides the global one.
    """

    name: str
    target: Any | None = None
    camera: Any | None = None
    clear_color: PrColor | None = None
    viewport_scissor: RectType | None = None
    order: int = 0
    min_layer: int | None = None
    max_layer: int | None = None
    screen_space: bool = False
    enabled: bool = True
    immediate: Callable[[DrawScope, str], None] | None = None


@dataclass(slots=True)
class RenderState:
    """GPU state attached to each draw item.

    Used to group (batch) draw calls that share identical state, so
    state changes are minimized at flush time.

    Attributes:
        scissor: Scissor rect in screen coordinates (x, y, w, h).
                 None means no scissor.
        blend_mode: The blend mode to use. Defaults to ALPHA.
        shader: The shader program to enable. None means the default shader.
    """

    scissor: RectType | None = None
    blend_mode: BlendMode = BlendMode.ALPHA
    shader: ShaderType | None = None

    def state_key(self) -> tuple:
        """Key for grouping/batching at flush time.

        Returns a comparable tuple used to decide whether two items can
        be batched together (identical state).
        """
        shader_id = id(self.shader) if self.shader else 0
        return (self.scissor, self.blend_mode, shader_id)

    def __eq__(self, other: object) -> bool:
        """Compares two states by their state keys."""
        if not isinstance(other, RenderState):
            return NotImplemented
        return self.state_key() == other.state_key()

    def __hash__(self) -> int:
        """Hashes the state key."""
        return hash(self.state_key())


# Default state singleton for reuse — avoids repeated allocation.
DEFAULT_RENDER_STATE = RenderState()


class RenderStateCache:
    """Maps ``RenderState`` objects to compact integer ids for batching."""

    def __init__(self) -> None:
        """Initializes the cache with the default state (id=0)."""
        self._state_to_id: dict[tuple, int] = {DEFAULT_RENDER_STATE.state_key(): 0}
        self._id_to_state: list[RenderState] = [DEFAULT_RENDER_STATE]

    def intern(
        self,
        *,
        scissor: RectType | None = None,
        blend_mode: BlendMode | int = BlendMode.ALPHA,
        shader: ShaderType | None = None,
    ) -> int:
        """Returns the compact id for the given state combination.

        Args:
            scissor: Optional scissor rect.
            blend_mode: Blend mode (BlendMode or int).
            shader: Optional shader.

        Returns:
            int: State id (0 is the default). Ids are stable per combination.
        """
        state = RenderState(
            scissor=scissor, blend_mode=BlendMode(blend_mode), shader=shader
        )
        key = state.state_key()
        state_id = self._state_to_id.get(key)
        if state_id is not None:
            return state_id
        state_id = len(self._id_to_state)
        self._state_to_id[key] = state_id
        self._id_to_state.append(state)
        return state_id

    def get(self, state_id: int) -> RenderState:
        """Retrieves a ``RenderState`` by its compact ``intern`` id.

        Args:
            state_id: State id previously returned by ``intern``.

        Returns:
            RenderState: The state associated with that id.
        """
        return self._id_to_state[state_id]

    def clear(self) -> None:
        """Empties the cache, leaving only the default state (id=0)."""
        self._state_to_id = {DEFAULT_RENDER_STATE.state_key(): 0}
        self._id_to_state = [DEFAULT_RENDER_STATE]

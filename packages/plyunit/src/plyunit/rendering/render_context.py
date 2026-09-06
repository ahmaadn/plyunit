"""Immutable render context carried through scene submission."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from plyunit.core.types import RectType, ShaderType

from .enum import BlendMode

if TYPE_CHECKING:
    from plyunit.core.components.transform import Transform2D


@dataclass(frozen=True, slots=True)
class RenderContext:
    """Resolved render state carried along during scene submission.

    Attributes:
        pass_name: Target render pass name.
        layer: Render layer used for ordering.
        z: Additional z value within the layer.
        submit_index_base: Optional submit index base for batching.
        visible: Set to False to skip submission.
        screen_space: True when positioned in screen space.
        scissor: Optional scissor rect.
        blend_mode: Active blend mode.
        shader: Optional shader.
        state_id: Compact state id from ``RenderStateCache``.
        y_sort: Enables Y sorting for this layer.
        y_sort_origin: Y origin used for sorting.
        world_transform: Source entity's world transform.
        render_transform: Final transform used when drawing.
    """

    pass_name: str = "world"
    layer: int = 0
    z: float = 0.0
    submit_index_base: int | None = None
    visible: bool = True
    screen_space: bool = False
    scissor: RectType | None = None
    blend_mode: BlendMode = BlendMode.ALPHA
    shader: ShaderType | None = None
    state_id: int = 0
    y_sort: bool = False
    y_sort_origin: float = 0.0
    world_transform: Transform2D | Any | None = None
    render_transform: Transform2D | Any | None = None

    def derive(self, **overrides: object) -> RenderContext:
        """Returns a derived ``RenderContext`` with certain fields replaced.

        Args:
            **overrides: Fields to replace on the new copy.

        Returns:
            RenderContext: New context produced via ``dataclasses.replace``.
        """
        return replace(self, **overrides)

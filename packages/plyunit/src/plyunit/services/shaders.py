"""Backend-neutral validation of numeric shader uniform values."""

from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Integral, Real

from plyunit._enums import ShaderUniform
from plyunit.core.types import UniformValue

_COMPONENT_COUNTS = {
    ShaderUniform.FLOAT: 1,
    ShaderUniform.VEC2: 2,
    ShaderUniform.VEC3: 3,
    ShaderUniform.VEC4: 4,
    ShaderUniform.INT: 1,
    ShaderUniform.IVEC2: 2,
    ShaderUniform.IVEC3: 3,
    ShaderUniform.IVEC4: 4,
    ShaderUniform.SAMPLER2D: 1,
}
_FLOAT_UNIFORM_TYPES = frozenset({
    ShaderUniform.FLOAT,
    ShaderUniform.VEC2,
    ShaderUniform.VEC3,
    ShaderUniform.VEC4,
})
_INT_MIN = -(2**31)
_INT_MAX = 2**31 - 1
_FLOAT_MAX = 3.4028234663852886e38


def uniform_components(
    value: UniformValue, uniform_type: ShaderUniform
) -> tuple[float, ...] | tuple[int, ...]:
    """Validate and convert one scalar or vector uniform.

    Args:
        value: A numeric scalar or sequence, not a backend pointer.
        uniform_type: Uniform type determining the component count and storage.

    Returns:
        A tuple of floats or signed 32-bit integers.

    Raises:
        TypeError: If the value or any component is not numeric.
        ValueError: If the component count, range, or integer precision is wrong.
    """
    if isinstance(value, Real):
        values = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = tuple(value)
    else:
        raise TypeError("uniform value must be a numeric scalar or sequence")

    expected = _COMPONENT_COUNTS[uniform_type]
    if len(values) != expected:
        raise ValueError(
            f"{uniform_type.name} requires exactly {expected} component(s)"
        )
    if any(not isinstance(component, Real) for component in values):
        raise TypeError("uniform components must be numeric")

    if uniform_type in _FLOAT_UNIFORM_TYPES:
        try:
            floats = tuple(float(component) for component in values)
        except OverflowError as exc:
            raise ValueError(
                "float uniform components must be finite 32-bit values"
            ) from exc
        if any(
            not math.isfinite(component) or abs(component) > _FLOAT_MAX
            for component in floats
        ):
            raise ValueError("float uniform components must be finite 32-bit values")
        return floats

    integers: list[int] = []
    for component in values:
        if not isinstance(component, Integral) and (
            not math.isfinite(component) or component != int(component)
        ):
            raise ValueError("integer uniform components must be whole numbers")
        integer = int(component)
        if not _INT_MIN <= integer <= _INT_MAX:
            raise ValueError(
                "integer uniform components must fit signed 32-bit storage"
            )
        integers.append(integer)
    return tuple(integers)


__all__ = ("uniform_components",)

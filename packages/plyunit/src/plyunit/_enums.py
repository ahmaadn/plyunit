from enum import Enum, IntEnum, auto
from typing import Any


class TextureFilter(Enum):
    TRILINEAR = auto()
    NEAREST = auto()
    LINEAR = auto()

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        key_upper = str(key).upper()
        return cls.__members__.get(key_upper, default)


class TextureWrap(Enum):
    CLAMP = auto()
    REPEAT = auto()
    MIRROR = auto()
    MIRROR_REPEAT = auto()

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        key_upper = str(key).upper()
        return cls.__members__.get(key_upper, default)


class ShaderUniform(IntEnum):
    """Uniform type IDs shared by every backend.

    The numeric values match the raylib ``SHADER_UNIFORM_*`` constants; other
    backends map them to their own representation internally.
    """

    FLOAT = 0  # Single float uniform.
    VEC2 = 1  # 2-component (float) vector uniform.
    VEC3 = 2  # 3-component (float) vector uniform.
    VEC4 = 3  # 4-component (float) vector uniform.
    INT = 4  # Single integer uniform.
    IVEC2 = 5  # 2-component (integer) vector uniform.
    IVEC3 = 6  # 3-component (integer) vector uniform.
    IVEC4 = 7  # 4-component (integer) vector uniform.
    SAMPLER2D = 8  # 2D texture sampler.

"""Public asset, animation, shader, font, and text exports."""

from __future__ import annotations

from .animations import AnimationClip, AnimationFrame, Animations
from .assets import Assets
from .shaders import ShaderHandle, Shaders, ShaderUniform
from .text import Text
from .types import (
    ConfigImage as ConfigImage,
    ConfigTexture as ConfigTexture,
    ShapedText as ShapedText,
    ShapeKey as ShapeKey,
    SpriteSheetAnimationConfig as SpriteSheetAnimationConfig,
    SpriteSheetConfig as SpriteSheetConfig,
    SpriteSheetFrameConfig as SpriteSheetFrameConfig,
    SpriteSheetGroupConfig as SpriteSheetGroupConfig,
    TemplateText as TemplateText,
    TextureData as TextureData,
    config_image_from_dict as config_image_from_dict,
    config_texture_from_dict as config_texture_from_dict,
)

__all__ = [
    "AnimationClip",
    "AnimationFrame",
    "Animations",
    "Assets",
    "ConfigImage",
    "ConfigTexture",
    "ShaderHandle",
    "ShaderUniform",
    "Shaders",
    "ShapeKey",
    "ShapedText",
    "SpriteSheetAnimationConfig",
    "SpriteSheetConfig",
    "SpriteSheetFrameConfig",
    "SpriteSheetGroupConfig",
    "TemplateText",
    "Text",
    "TextureData",
    "config_image_from_dict",
    "config_texture_from_dict",
]

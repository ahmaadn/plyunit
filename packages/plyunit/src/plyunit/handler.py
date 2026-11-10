from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

if TYPE_CHECKING:
    from plyunit.backends.integrations import (
        Font,
        Image,
        RenderTexture,
        Shader,
        StreamingTexture,
        Texture2D,
    )

__all__ = ("Font", "Image", "RenderTexture", "Shader", "StreamingTexture", "Texture2D")


__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "Font": "plyunit.backends.integrations",
        "Image": "plyunit.backends.integrations",
        "RenderTexture": "plyunit.backends.integrations",
        "Shader": "plyunit.backends.integrations",
        "StreamingTexture": "plyunit.backends.integrations",
        "Texture2D": "plyunit.backends.integrations",
    },
    global_dict=globals(),
    all_exports=__all__,
)

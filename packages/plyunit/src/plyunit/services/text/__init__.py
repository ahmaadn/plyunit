from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

from .shape import ShapeCache

if TYPE_CHECKING:
    from plyunit.backends.integrations import Font, Text

__all__ = ("Font", "ShapeCache", "Text")


__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "Font": "plyunit.backends.integrations",
        "Text": "plyunit.backends.integrations",
    },
    global_dict=globals(),
    all_exports=__all__,
)

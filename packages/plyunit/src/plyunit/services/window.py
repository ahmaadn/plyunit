from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

if TYPE_CHECKING:
    from plyunit.backends.integrations import Window

__all__ = ("Window",)


__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "Window": "plyunit.backends.integrations",
    },
    global_dict=globals(),
    all_exports=__all__,
)

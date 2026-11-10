from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

if TYPE_CHECKING:
    from plyunit.backends.imgui import ImGui

__all__ = ("ImGui",)


__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "ImGui": "plyunit.backends.imgui",
    },
    global_dict=globals(),
    all_exports=__all__,
)

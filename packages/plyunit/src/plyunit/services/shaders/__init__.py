from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

from .uniform import uniform_components

if TYPE_CHECKING:
    from plyunit.backends.integrations import Shader, Shaders

__all__ = ("Shader", "Shaders", "uniform_components")


__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "Shader": "plyunit.backends.integrations",
        "Shaders": "plyunit.backends.integrations",
    },
    global_dict=globals(),
    all_exports=__all__,
)

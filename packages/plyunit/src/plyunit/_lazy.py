# plyunit/_lazy.py
from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any


def create_lazy_loader(
    package_name: str,
    lazy_modules: Mapping[str, str],
    global_dict: dict[str, Any],
    all_exports: Sequence[str] | None = None,
) -> tuple[Callable[[str], Any], Callable[[], list[str]]]:
    """Membuat fungsi __getattr__ dan __dir__ generik untuk lazy import modul/paket."""

    def __getattr__(name: str) -> Any:
        module_name = lazy_modules.get(name)
        if module_name is None:
            raise AttributeError(f"module {package_name!r} has no attribute {name!r}")

        module = importlib.import_module(module_name)
        try:
            value = getattr(module, name)
        except AttributeError:
            try:
                value = importlib.import_module(f"{module_name}.{name}")
            except ImportError:
                raise AttributeError(
                    f"module {module_name!r} has no attribute {name!r}"
                ) from None

        global_dict[name] = value
        return value

    def __dir__() -> list[str]:
        base = set(global_dict) | set(lazy_modules)
        if all_exports is not None:
            base |= set(all_exports)
        return sorted(base)

    return __getattr__, __dir__

"""Architectural guards for ports-only dependencies in backend-neutral code."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / "src" / "plyunit"
DOMAIN_ROOTS = ("core", "events", "rendering", "services", "tilemap", "utils")
VENDORS = ("pyray", "raylib", "pymunk", "imgui", "imgui_bundle", "OpenGL")


def _imports(path: Path) -> list[str]:
    """Resolve absolute, relative, and literal dynamic imports in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = path.relative_to(PKG.parent).with_suffix("")
    parts = relative.parts
    package = ".".join(parts[:-1])
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = resolve_name("." * node.level + module, package)
            result.append(module)
            result.extend(module + "." + alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in {"import_module", "__import__"}:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    result.append(arg.value)
    return result


def _forbidden(module: str) -> bool:
    """Reject concrete vendors and backend selectors, including typing imports."""
    if module.split(".")[0] in VENDORS:
        return True
    if module == "plyunit.backends" or module.startswith("plyunit.backends."):
        return not (module == "plyunit.backends.ports" or module.startswith("plyunit.backends.ports."))
    return False


@pytest.mark.parametrize("domain", DOMAIN_ROOTS)
def test_domain_dependencies_use_ports_only(domain: str) -> None:
    root = PKG / domain
    assert root.is_dir(), f"Missing neutral domain: {root}"
    offenders = [
        f"{path.relative_to(PKG)}: {module}"
        for path in root.rglob("*.py")
        for module in _imports(path)
        if _forbidden(module)
    ]
    assert not offenders, "Concrete backend imports in neutral code:\n" + "\n".join(offenders)


def test_ports_do_not_import_concrete_backends() -> None:
    offenders = [
        f"{path.relative_to(PKG)}: {module}"
        for path in (PKG / "backends" / "ports").rglob("*.py")
        for module in _imports(path)
        if _forbidden(module)
    ]
    assert not offenders, "Concrete backend imports in ports:\n" + "\n".join(offenders)


def test_resource_ports_do_not_expose_native_objects() -> None:
    """Native fields and constructors belong to concrete backend handles."""
    from plyunit.backends.ports import handler

    for name in handler.__all__:
        handle = getattr(handler, name)
        if isinstance(handle, type) and name.endswith("Handle"):
            assert not any(field.startswith("raw_") for field in vars(handle)), name
            assert "from_raw" not in vars(handle), name
    assert "locations" not in vars(handler.ShaderHandle)

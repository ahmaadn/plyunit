"""Architectural guard: domain layers must not import concrete backends at runtime."""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "src" / "plyunit"
CORE_ROOT = PKG / "core"
COMPONENTS_ROOT = PKG / "core" / "components"
ENGINE_ROOTS = [
    PKG / "core",
    PKG / "scene",
    PKG / "rendering",
    PKG / "audio",
    PKG / "assets",
    PKG / "events",
    PKG / "tilemap",
    PKG / "services",
]

# Core may import protocol interfaces; concrete vendor backends are forbidden.
FORBIDDEN_IN_CORE = (
    "plyunit.backends.integrations",
    "plyunit.backends.physics",
    "plyunit.backends.imgui",
)
# Engine domains may import backends.* facades only via selector packages later;
# concrete vendor packages stay forbidden at runtime.
FORBIDDEN_IN_ENGINE = (
    "plyunit.backends.integrations.raylib",
    "plyunit.backends.physics.pymunk",
    "plyunit.backends.imgui.raylib",
)


def _runtime_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._in_type_checking = False

        def visit_If(self, node: ast.If) -> None:
            is_tc = False
            test = node.test
            if (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                or (
                    isinstance(test, ast.Attribute)
                    and isinstance(test.value, ast.Name)
                    and test.value.id == "typing"
                    and test.attr == "TYPE_CHECKING"
                )
            ):
                is_tc = True
            prev = self._in_type_checking
            if is_tc:
                self._in_type_checking = True
            self.generic_visit(node)
            self._in_type_checking = prev

        def visit_Import(self, node: ast.Import) -> None:
            if self._in_type_checking:
                return
            for alias in node.names:
                imports.append(alias.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if self._in_type_checking:
                return
            mod = node.module or ""
            imports.append(mod)

    Visitor().visit(tree)
    return imports


def _assert_no_forbidden(root: Path, forbidden: tuple[str, ...]) -> None:
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for mod in _runtime_imports(path):
            for bad in forbidden:
                if mod == bad or mod.startswith(bad + "."):
                    offenders.append(f"{path.relative_to(root.parent.parent)}: {mod}")
    assert not offenders, "Forbidden runtime imports:\n" + "\n".join(offenders)


def test_core_does_not_import_backends() -> None:
    _assert_no_forbidden(CORE_ROOT, FORBIDDEN_IN_CORE)
    if COMPONENTS_ROOT.exists():
        _assert_no_forbidden(COMPONENTS_ROOT, FORBIDDEN_IN_CORE)


def test_engine_domains_do_not_import_concrete_backends() -> None:
    for root in ENGINE_ROOTS:
        if root.exists():
            _assert_no_forbidden(root, FORBIDDEN_IN_ENGINE)



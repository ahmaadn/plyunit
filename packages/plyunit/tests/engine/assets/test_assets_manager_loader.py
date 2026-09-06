from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import plyunit as pu
import plyunit.assets.assets as assets_module
from plyunit.assets.types import ConfigTexture, TextureData

unit_module = importlib.import_module("plyunit.core.units.unit")


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> pu.UnitRegistry:
    registry = pu.UnitRegistry()
    monkeypatch.setattr(unit_module, "units", registry)
    monkeypatch.setattr(pu, "units", registry, raising=False)
    return registry


class DummyLoader:
    def __init__(self) -> None:
        self.texture_calls: list[Path] = []
        self.dict_calls: list[tuple[object, Path | None]] = []
        self.default = ConfigTexture(
            filter="nearest",
            wrap="clamp",
            mipmap=False,
            srgb=True,
            premultiply_alpha=False,
            color_key=(0, 0, 0, 255),
        )

    def load_texture(self, path: Path, **_kwargs):
        self.texture_calls.append(path)

        class FakeTexture:
            width = 100
            height = 100

            def __init__(self, name):
                self.name = name

        return FakeTexture(f"texture:{path.name}")

    def load_texture_from_dict(
        self, data, *, image_path: Path | None = None
    ):
        self.dict_calls.append((data, image_path))

        class FakeTexture:
            width = 100
            height = 100

            def __init__(self, name):
                self.name = name

        # pyrefly: ignore [missing-attribute]
        return FakeTexture(f"dict:{image_path.name}")

    def unload_texture(self, texture):
        self.texture_calls.append(Path(f"unload:{texture}"))


def test_loader_load_texture_and_apply_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class FakeImage:
        width = 8
        height = 4

    class FakeColor:
        def __init__(self, r: int, g: int, b: int, a: int) -> None:
            self.r = int(r)
            self.g = int(g)
            self.b = int(b)
            self.a = int(a)

    def load_image(path: str | Path) -> FakeImage:
        calls["load_image"] = str(path)
        return FakeImage()

    def image_color_replace(image: FakeImage, _from: FakeColor, _to: FakeColor) -> None:
        _ = image, _from, _to
        calls["color_replace"] = True

    def image_alpha_premultiply(image: FakeImage) -> None:
        _ = image
        calls["alpha"] = True

    def load_texture_from_image(image: FakeImage) -> str:
        _ = image
        calls["load_texture"] = True
        return "tex"

    def unload_image(image: FakeImage) -> None:
        _ = image
        calls["unload"] = True

    def gen_texture_mipmaps(texture: str) -> None:
        _ = texture
        calls["mipmap"] = True

    def set_texture_filter(texture: str, value: str) -> None:
        _ = texture
        if value not in {"nearest", "linear"}:
            raise ValueError(f"Mode filter tidak dikenal {value!r}")
        calls["filter"] = {"nearest": 11, "linear": 12}.get(value, value)

    def set_texture_wrap(texture: str, value: str) -> None:
        _ = texture
        if value not in {"clamp", "mirror", "repeat"}:
            raise ValueError(f"Mode wrap tidak dikenal '{value}'")
        calls["wrap"] = {"clamp": 22, "mirror": 23, "repeat": 24}.get(value, value)

    import plyunit.backends.integrations.raylib.assets.assets_loader as loader_module
    from plyunit.backends.integrations.raylib.assets import AssetsLoader  # noqa: PLC0415

    monkeypatch.setattr(loader_module, "load_image", load_image)
    monkeypatch.setattr(loader_module.pr, "image_color_replace", image_color_replace)
    monkeypatch.setattr(
        loader_module.pr, "image_alpha_premultiply", image_alpha_premultiply
    )
    monkeypatch.setattr(loader_module.pr, "Color", FakeColor)
    monkeypatch.setattr(
        loader_module, "load_texture_from_image", load_texture_from_image
    )
    monkeypatch.setattr(loader_module, "unload_image", unload_image)
    monkeypatch.setattr(loader_module, "gen_texture_mipmaps", gen_texture_mipmaps)
    monkeypatch.setattr(loader_module, "set_texture_filter", set_texture_filter)
    monkeypatch.setattr(loader_module, "set_texture_wrap", set_texture_wrap)

    loader = AssetsLoader()
    texture = loader.load_texture(
        Path("hero.png"),
        alpha_premultiply=True,
        filter_mode="nearest",
        wrap_mode="clamp",
        mipmap=True,
    )

    assert texture == "tex"
    assert calls["color_replace"] is True
    assert calls["alpha"] is True
    assert calls["filter"] == 11
    assert calls["wrap"] == 22
    assert calls["mipmap"] is True

    # Validation paths use the real module functions
    real_set_filter = importlib.import_module(
        "plyunit.backends.integrations.raylib.assets.assets_loader"
    )
    # Call through unpatched names by re-binding FILTER maps and using original
    # implementations that live on the module (we overwrote them above).
    # Restore originals for the validation assertions:
    importlib.reload(loader_module)

    with pytest.raises(ValueError, match="Mode filter tidak dikenal"):
        loader_module.set_texture_filter("tex", "unknown")

    with pytest.raises(ValueError, match="Mode wrap tidak dikenal"):
        loader_module.set_texture_wrap("tex", "unknown")

    _ = real_set_filter


def test_asset_manager_load_asset_from_json_and_image(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
) -> None:
    _ = isolated_registry

    loader = DummyLoader()
    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(asset_base_path=tmp_path, loader=loader)

    image_path = tmp_path / "hero.png"
    image_path.write_text("x", encoding="utf-8")

    config_path = tmp_path / "hero.json"
    config_path.write_text(
        '{"id": "hero", "image_path": "hero.png", "texture": {"wrap": "clamp"}}',
        encoding="utf-8",
    )

    manager.load_asset("hero.json")

    assert loader.dict_calls
    # pyrefly: ignore [missing-attribute]
    assert manager.get_asset("hero").name == "dict:hero.png"

    standalone_path = tmp_path / "coin.png"
    standalone_path.write_text("x", encoding="utf-8")

    manager.load_asset("coin.png")
    assert loader.texture_calls == [standalone_path]
    # pyrefly: ignore [missing-attribute]
    assert manager["coin"].name == "texture:coin.png"


def test_asset_manager_load_spritesheet(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
) -> None:
    _ = isolated_registry

    loader = DummyLoader()
    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(asset_base_path=tmp_path, loader=loader)

    config_path = tmp_path / "sheet.json"
    config_path.write_text(
        '{"id": "my_sheet", "type": "spritesheet", "image_path": "sheet.png", "regions": {"tile1": {"rect": [0,0,16,16]}}}',
        encoding="utf-8",
    )

    image_path = tmp_path / "sheet.png"
    image_path.write_text("x", encoding="utf-8")

    manager.load_spritesheet("sheet.json")

    assert "my_sheet" in manager._textures
    assert manager.get_texture_data("tile1").parent_id == "my_sheet"


def test_asset_manager_resolves_image_next_to_nested_sidecar(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
) -> None:
    """An editor sidecar may store image_path as a bare local file name."""
    _ = isolated_registry

    folder = tmp_path / "sprites"
    folder.mkdir()
    image_path = folder / "sheet.png"
    image_path.write_text("x", encoding="utf-8")
    config_path = folder / "sheet.json"
    config_path.write_text(
        '{"id": "sheet", "type": "spritesheet", '
        '"image_path": "sheet.png", '
        '"regions": {"tile1": [0, 0, 16, 16]}}',
        encoding="utf-8",
    )

    loader = DummyLoader()
    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(asset_base_path=tmp_path, loader=loader)
    manager.load_spritesheet("sprites/sheet.json")

    assert loader.dict_calls[0][1] == image_path
    assert manager.get_texture_data("tile1").parent_id == "sheet"


def test_asset_manager_falls_back_to_sidecar_for_prefixed_image_path(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
) -> None:
    """A legacy asset-root path can still use the image next to the sidecar."""
    _ = isolated_registry

    folder = tmp_path / "examples" / "data" / "tile"
    folder.mkdir(parents=True)
    image_path = folder / "sheet.png"
    image_path.write_text("x", encoding="utf-8")
    config_path = folder / "sheet.json"
    config_path.write_text(
        '{"id": "sheet", "type": "spritesheet", '
        '"image_path": "tile/sheet.png", "regions": {}}',
        encoding="utf-8",
    )

    loader = DummyLoader()
    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(asset_base_path=tmp_path, loader=loader)
    manager.load_spritesheet("examples/data/tile/sheet.json")

    assert loader.dict_calls[0][1] == image_path


def test_asset_manager_rejects_path_traversal(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
) -> None:
    _ = isolated_registry

    base_path = tmp_path / "data"
    base_path.mkdir()

    (tmp_path / "outside.png").write_text("x", encoding="utf-8")

    manager = assets_module.Assets(
        asset_base_path=base_path,
        # pyrefly: ignore [bad-argument-type]
        loader=DummyLoader(),
    )

    with pytest.raises(ValueError, match="escapes base path"):
        manager.load_asset("../outside.png")


def test_asset_manager_rejects_config_image_outside_base(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
) -> None:
    _ = isolated_registry

    base_path = tmp_path / "data"
    base_path.mkdir()

    (tmp_path / "outside.png").write_text("x", encoding="utf-8")

    config_path = base_path / "evil.json"
    config_path.write_text(
        '{"id": "evil", "image_path": "../outside.png", "texture": {}}',
        encoding="utf-8",
    )

    manager = assets_module.Assets(
        asset_base_path=base_path,
        # pyrefly: ignore [bad-argument-type]
        loader=DummyLoader(),
    )

    with pytest.raises(ValueError, match="escapes base path"):
        manager.load_asset("evil.json")


def test_asset_manager_load_from_dict_auto_image_and_missing(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
) -> None:
    _ = isolated_registry

    loader = DummyLoader()
    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(asset_base_path=tmp_path, loader=loader)

    config_path = tmp_path / "enemy.json"
    config_path.write_text('{"id": "enemy", "texture": {}}', encoding="utf-8")

    image_path = tmp_path / "enemy.png"
    image_path.write_text("x", encoding="utf-8")

    config_data = {
        "id": "enemy",
        "texture": {},
        "config_path": config_path,
        "image_path": "enemy.png",
    }
    manager.load_from_dict(config_data, asset_id=None)
    # pyrefly: ignore [missing-attribute]
    assert manager.get_asset("enemy").name == "dict:enemy.png"

    missing_path = tmp_path / "ghost.json"
    missing_path.write_text('{"id": "ghost", "texture": {}}', encoding="utf-8")

    config_data = {
        "id": "ghost",
        "texture": {},
        "config_path": missing_path,
        "image_path": "ghost.png",
    }
    with pytest.raises(FileNotFoundError):
        manager.load_from_dict(config_data, asset_id=None)


def test_asset_manager_load_folder_processes_configs_and_images(
    isolated_registry: pu.UnitRegistry,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_registry

    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(asset_base_path=tmp_path, loader=DummyLoader())

    folder = tmp_path / "sprites"
    folder.mkdir()

    (folder / "hero.png").write_text("x", encoding="utf-8")
    (folder / "hero.json").write_text(
        '{"id": "hero", "image_path": "sprites/hero.png", "texture": {}}',
        encoding="utf-8",
    )
    (folder / "coin.png").write_text("x", encoding="utf-8")

    called: list[Path] = []

    def fake_load_asset(path: str, *, asset_id: str | None = None) -> None:
        _ = asset_id
        called.append(Path(path))

    monkeypatch.setattr(manager, "load_asset", fake_load_asset)

    manager.load_folder("sprites", allow_extensions=[".png"])

    assert Path("sprites") / "hero.json" in called
    assert Path("sprites") / "coin.png" in called

    with pytest.raises(FileNotFoundError, match="Folder tidak ada"):
        manager.load_folder("missing")


def test_asset_manager_unload_asset_paths(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_registry

    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(loader=DummyLoader())
    manager._textures["hero"] = TextureData(
        texture="tex",  # type: ignore[arg-type]
        parent_id="hero",
        source_rect=(0, 0, 0, 0),
    )

    loader = manager._loader
    calls: list[str] = []
    monkeypatch.setattr(loader, "unload_texture", lambda tex: calls.append(str(tex)))

    manager._unload_asset("hero")
    assert "hero" not in manager._textures
    assert calls == ["tex"]

    manager._unload_asset("missing")


def test_asset_manager_destroy_unloads_cached_textures(
    isolated_registry: pu.UnitRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = isolated_registry

    # pyrefly: ignore [bad-argument-type]
    manager = assets_module.Assets(loader=DummyLoader())
    manager._textures["hero"] = TextureData(
        texture="tex:hero",  # type: ignore[arg-type]
        parent_id="hero",
        source_rect=(0, 0, 0, 0),
    )
    manager._textures["coin"] = TextureData(
        texture="tex:coin",  # type: ignore[arg-type]
        parent_id="coin",
        source_rect=(0, 0, 0, 0),
    )

    loader = manager._loader
    calls: list[str] = []
    monkeypatch.setattr(loader, "unload_texture", lambda tex: calls.append(str(tex)))

    manager.destroy()

    assert calls == ["tex:hero", "tex:coin"]
    assert manager._textures == {}

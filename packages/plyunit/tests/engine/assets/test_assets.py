from __future__ import annotations

from pathlib import Path

from plyunit.backends.integrations.raylib.assets import AssetsLoader


def test_load_texture_from_dict_preserves_resolved_image_path(
    monkeypatch, tmp_path: Path
) -> None:
    loader = AssetsLoader()
    captured: dict[str, Path] = {}

    def fake_load_texture(path: Path, **_kwargs):
        captured["path"] = path
        return object()

    monkeypatch.setattr(
        "plyunit.backends.integrations.raylib.assets.assets_loader.load_texture",
        fake_load_texture,
    )

    resolved_path = tmp_path / "background" / "Background_0.png"
    resolved_path.parent.mkdir(parents=True)

    texture = loader.load_texture_from_dict(
        {
            "id": "background_0",
            "image_path": "Background_0.png",
            "texture": {
                "filter": "linear",
                "wrap": "clamp",
                "mipmap": False,
                "premultiply_alpha": False,
            },
        },
        image_path=resolved_path,
    )

    assert captured["path"] == resolved_path
    assert texture is not None

from __future__ import annotations

import importlib
import json
from itertools import count
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import plyunit.backends.integrations.raylib.text as text_mod
from plyunit.backends.integrations.raylib.handler import Font
from plyunit.backends.integrations.raylib.text import Text
from plyunit.backends.ports.text import TemplateText
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.core.units.unit_registry import UnitRegistry
from plyunit.services.text import ShapeCache, build_default_templates


def _fake_font(*, tex_id: int = 7, base_size: int = 16, advance: int = 8):
    return SimpleNamespace(
        baseSize=base_size,
        glyphCount=1,
        glyphPadding=0,
        texture=SimpleNamespace(id=tex_id, width=32, height=32, format=7, mipmaps=1),
        recs=[SimpleNamespace(x=0.0, y=0.0, width=8.0, height=12.0)],
        glyphs=[SimpleNamespace(offsetX=0, offsetY=0, advanceX=advance)],
    )


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch):
    registry = UnitRegistry()
    unit_mod = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(unit_mod, "units", registry)
    default = _fake_font(tex_id=1)
    ids = count(2)
    image = SimpleNamespace(width=32, height=32)
    fake_pr = SimpleNamespace(
        get_font_default=Mock(return_value=default),
        load_font=Mock(side_effect=lambda path: _fake_font(tex_id=next(ids))),
        load_font_from_image=Mock(side_effect=lambda *_: _fake_font(tex_id=next(ids))),
        load_image=Mock(return_value=image),
        is_image_valid=Mock(return_value=True),
        is_font_valid=Mock(
            side_effect=lambda raw: raw.baseSize > 0 and raw.glyphCount > 0
        ),
        unload_image=Mock(),
        unload_font=Mock(),
        Color=Mock(side_effect=lambda *channels: channels),
        get_glyph_index=Mock(return_value=0),
    )
    monkeypatch.setattr(text_mod, "pr", fake_pr)
    renderer = SimpleNamespace(
        canvas=SimpleNamespace(draw_text=Mock()), render_shaped_text=Mock()
    )
    service = Text(renderer=renderer)
    yield SimpleNamespace(
        text=service,
        pr=fake_pr,
        renderer=renderer,
        default=default,
        image=image,
        registry=registry,
    )
    fake_pr.unload_font.side_effect = None
    for item in registry.group(Text):
        item.destroy()


def test_text_draw_push_and_measure(env) -> None:
    env.text.draw("hello", pos=(1, 2), color=(255, 0, 0, 255), font_size=20)
    assert env.renderer.canvas.draw_text.call_args.kwargs["text"] == "hello"
    env.text.push("world", pos=(3, 4), z=1, layer=2)
    shaped = env.renderer.render_shaped_text.call_args.args[0]
    assert shaped.offsets_xy.shape[0] == len("world")
    assert shaped.texture is env.text.get_font().texture
    assert env.text.measure("abc", font_size=16) == (27, 16)


def test_text_loads_fonts_and_templates_from_json_config(tmp_path, env) -> None:
    config = {
        "fonts": {
            "main": {"path": "main.ttf"},
            "missing_path": {},
            "bitmap": {"path": "font.PNG", "color_key": [1, 2, 3, 4], "first_char": 65},
        },
        "templates": {"title": {"font": "main", "spacing": 1, "size": 24}},
    }
    path = tmp_path / "font.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    env.text.load(path)
    assert isinstance(env.text.get_font("main"), Font)
    assert isinstance(env.text.get_font("bitmap"), Font)
    assert env.text.get_template("title") == TemplateText("main", 1.0, 24)
    assert "missing_path" not in env.text._fonts
    env.pr.load_font.assert_called_once_with("main.ttf")
    env.pr.load_font_from_image.assert_called_once_with(env.image, (1, 2, 3, 4), 65)
    env.pr.unload_image.assert_called_once_with(env.image)


def test_config_reader_is_injectable_without_creating_a_font_wrapper(env) -> None:
    reader = Mock(return_value={"templates": {"hud": {"size": 14}}})
    other = Text(tags={"hud"}, config_reader=reader)
    other.load("hud.json")
    reader.assert_called_once_with("hud.json")
    assert other.get_template("hud") == TemplateText("default", 0.0, 14)
    assert other.tags == {"service", "text", "hud"}


def test_missing_config_logs_and_keeps_existing_templates(env, caplog) -> None:
    reader = Mock(return_value=None)
    other = Text(config_reader=reader)
    before = other.get_template("base")
    other.load("missing.json")
    assert other.get_template("base") is before
    assert "Failed to load config" in caplog.text


@pytest.mark.parametrize(
    "config", [{"fonts": []}, {"templates": []}, {"fonts": {"bad": []}}]
)
def test_malformed_config_sections_raise_actionable_errors(env, config) -> None:
    other = Text(config_reader=Mock(return_value=config))
    with pytest.raises(ValueError, match="mapping"):
        other.load("bad.json")


def test_reloading_font_invalidates_old_handle_shapes_and_glyph_cache(env) -> None:
    old = env.text.load_font("main", "first.ttf")
    env.text.set_template("title", "main", spacing=0, size=16)
    env.text["title"]
    first_shape = env.text.shape("AA")
    assert env.text._glyph_index_caches["main"] == {65: 0}
    raw = _fake_font(tex_id=10, advance=12)
    env.pr.load_font.side_effect = None
    env.pr.load_font.return_value = raw
    previous_raw = old.raw_font
    replacement = env.text.load_font("main", "second.ttf")
    env.pr.unload_font.assert_called_once_with(previous_raw)
    assert old.raw_font is None and not old._valid
    assert env.text._shape_cache._store == {}
    assert "main" not in env.text._glyph_index_caches
    second_shape = env.text.shape("AA")
    assert second_shape is not first_shape
    assert second_shape.texture is replacement.texture
    assert second_shape.texture.texture_id != first_shape.texture.texture_id
    assert second_shape.total_width == 24


def test_default_font_fallback_on_failed_load_keeps_previous_font_and_shape(
    env,
) -> None:
    previous = env.text.load_font("main", "first.ttf")
    env.text.set_template("title", "main", spacing=0)
    shape = env.text["title"].shape("AA")
    env.pr.load_font.side_effect = None
    env.pr.load_font.return_value = env.default
    with pytest.raises(OSError, match="returned the default font"):
        env.text.load_font("main", "missing.ttf")
    assert env.text.get_font("main") is previous
    assert previous._valid
    assert env.text.shape("AA") is shape
    env.pr.unload_font.assert_not_called()
    assert env.default.texture.id == 1


def test_invalid_loaded_font_is_released_without_replacing_previous_font(env) -> None:
    previous = env.text.load_font("main", "first.ttf")
    invalid = _fake_font(tex_id=9, base_size=0)
    env.pr.load_font.side_effect = None
    env.pr.load_font.return_value = invalid
    with pytest.raises(OSError, match="failed to load font"):
        env.text.load_font("main", "bad.ttf")
    env.pr.unload_font.assert_called_once_with(invalid)
    assert env.text.get_font("main") is previous


def test_zero_id_font_is_released_when_default_is_also_unavailable(env) -> None:
    invalid = _fake_font(tex_id=0)
    env.pr.load_font.side_effect = None
    env.pr.load_font.return_value = invalid
    env.pr.get_font_default.return_value = _fake_font(tex_id=0, base_size=0)
    with pytest.raises(OSError, match="failed to load font"):
        env.text.load_font("main", "bad.ttf")
    env.pr.unload_font.assert_called_once_with(invalid)
    assert env.text._fonts == {}


def test_new_font_is_released_when_previous_font_unload_fails(env) -> None:
    previous = env.text.load_font("main", "first.ttf")
    new_raw = _fake_font(tex_id=9)
    env.pr.load_font.side_effect = None
    env.pr.load_font.return_value = new_raw
    previous_raw = previous.raw_font

    def unload(raw):
        if raw is previous_raw:
            raise RuntimeError("cannot release previous")

    env.pr.unload_font.side_effect = unload
    with pytest.raises(RuntimeError, match="cannot release previous"):
        env.text.load_font("main", "second.ttf")
    assert env.pr.unload_font.call_args.args[0] is new_raw
    assert env.text.get_font("main") is previous
    assert previous._valid


def test_handle_creation_failure_releases_loaded_font(env, monkeypatch) -> None:
    raw = _fake_font(tex_id=9)
    env.pr.load_font.side_effect = None
    env.pr.load_font.return_value = raw
    monkeypatch.setattr(Font, "from_raw", Mock(side_effect=RuntimeError("wrap failed")))
    with pytest.raises(RuntimeError, match="wrap failed"):
        env.text.load_font("main", "main.ttf")
    env.pr.unload_font.assert_called_once_with(raw)
    assert "main" not in env.text._fonts


def test_bitmap_image_is_released_when_font_creation_raises(env) -> None:
    env.pr.load_font_from_image.side_effect = RuntimeError("invalid bitmap")
    with pytest.raises(RuntimeError, match="invalid bitmap"):
        env.text.load_font("bitmap", "font.PNG")
    env.pr.unload_image.assert_called_once_with(env.image)
    assert "bitmap" not in env.text._fonts


def test_invalid_bitmap_image_is_released_before_font_creation(env) -> None:
    env.pr.is_image_valid.return_value = False
    with pytest.raises(OSError, match="bitmap font image"):
        env.text.load_font("bitmap", "font.png")
    env.pr.load_font_from_image.assert_not_called()
    env.pr.unload_image.assert_called_once_with(env.image)


def test_pre_window_default_font_is_not_cached_and_recovers_after_setup(env) -> None:
    invalid = _fake_font(tex_id=0, base_size=0)
    env.pr.get_font_default.return_value = invalid
    with pytest.raises(RuntimeError, match="initialize the window first"):
        env.text.shape("A")
    assert env.text._fonts == {}
    assert env.text._shape_cache._store == {}
    env.pr.get_font_default.return_value = env.default
    assert env.text.shape("A").total_width > 0
    assert env.text.get_font().raw_font is env.default


def test_default_font_refresh_invalidates_cached_shapes_and_glyph_indices(env) -> None:
    first_font = env.text.get_font()
    first_shape = env.text.shape("AA", spacing=0)
    env.default.baseSize = 0
    replacement = _fake_font(tex_id=9, advance=12)
    env.pr.get_font_default.return_value = replacement
    next_shape = env.text.shape("AA", spacing=0)
    assert next_shape is not first_shape
    assert next_shape.total_width == 24
    assert first_font.raw_font is None and not first_font._valid
    assert env.pr.get_glyph_index.call_count == 2
    env.pr.unload_font.assert_not_called()


def test_custom_font_access_does_not_require_fetching_default_font(env) -> None:
    font = env.text.load_font("main", "main.ttf")
    env.text.set_template("title", "main", spacing=0)
    env.pr.get_font_default.reset_mock()
    env.pr.get_font_default.side_effect = RuntimeError("default unavailable")
    assert env.text.get_font("main") is font
    assert env.text["title"].measure("AA") == (16, 16)
    env.pr.get_font_default.assert_not_called()


def test_template_preserves_requested_font_name_until_later_load(env) -> None:
    env.text.set_template("title", "later", spacing=0)
    first = env.text["title"].shape("AA")
    assert first.texture is env.text.get_font().texture
    loaded = env.text.load_font("later", "later.ttf")
    second = env.text.shape("AA")
    assert second.texture is loaded.texture
    assert second is not first
    assert env.text.get_template("title").font_name == "later"


def test_unload_fonts_never_unloads_or_mutates_default_and_clears_caches(env) -> None:
    default = env.text.get_font()
    custom = env.text.load_font("main", "main.ttf")
    custom_raw = custom.raw_font
    env.text.shape("AA")
    env.text.set_template("title", "main", spacing=0)
    env.text["title"].shape("AA")
    env.text.unload_fonts()
    env.text.unload_fonts()
    env.pr.unload_font.assert_called_once_with(custom_raw)
    assert env.default.texture.id == 1
    assert env.default.baseSize == 16
    assert custom.raw_font is None and not custom._valid
    assert default.raw_font is None and not default._valid
    assert env.text._glyph_index_caches == {}
    assert env.text._shape_cache._store == {}
    assert env.text._fonts == {}
    assert env.text.shape("AA").texture is env.text.get_font().texture


def test_unload_fonts_attempts_other_resources_and_preserves_failures_for_retry(
    env,
) -> None:
    first = env.text.load_font("first", "first.ttf")
    second = env.text.load_font("second", "second.ttf")
    first_raw = first.raw_font

    def unload(raw):
        if raw is first_raw:
            raise RuntimeError("first failed")

    env.pr.unload_font.side_effect = unload
    with pytest.raises(ExceptionGroup, match="failed to unload fonts") as caught:
        env.text.unload_fonts()
    assert len(caught.value.exceptions) == 1
    assert env.text.get_font("first") is first
    assert first._valid
    assert second.raw_font is None and not second._valid
    assert env.pr.unload_font.call_count == 2
    env.pr.unload_font.side_effect = None
    env.text.unload_fonts()
    assert first.raw_font is None


def test_destroy_without_an_app_unloads_fonts_and_unregisters_service(env) -> None:
    custom = env.text.load_font("main", "main.ttf")
    env.text.destroy()
    assert custom.raw_font is None
    assert not env.registry.contains(env.text)
    env.pr.unload_font.assert_called_once()


def test_registry_detach_releases_font_resources(env) -> None:
    app = ServiceUnit(name="TestApp")
    env.registry.activate_app(app)
    custom = env.text.load_font("main", "main.ttf")
    env.registry.unregister(env.text)
    assert custom.raw_font is None
    env.pr.unload_font.assert_called_once()


def test_default_templates_are_independent_immutable_values() -> None:
    first = build_default_templates()
    second = build_default_templates()
    first["base"] = TemplateText("custom", 9, 99)
    assert second["base"] == TemplateText("default", None, 16)


def test_shape_cache_is_bounded_and_refreshes_lru_recency(env) -> None:
    env.text._shape_cache = ShapeCache(maxsize=2)
    first = env.text.shape("A")
    second = env.text.shape("B")
    assert env.text.shape("A") is first
    env.text.shape("C")
    assert len(env.text._shape_cache._store) == 2
    assert env.text.shape("A") is first
    assert env.text.shape("B") is not second
    assert len(env.text._shape_cache._store) == 2


def test_shape_cache_can_be_disabled_and_rejects_negative_capacity(env) -> None:
    env.text._shape_cache = ShapeCache(maxsize=0)
    assert env.text.shape("A") is not env.text.shape("A")
    assert env.text._shape_cache._store == {}
    with pytest.raises(ValueError, match="capacity"):
        ShapeCache(maxsize=-1)

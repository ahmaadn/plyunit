"""Bounded lifecycle smoke tests for the published example entry points.

Raylib I/O and the native batch are replaced at adapter boundaries. Application,
service, scene, resource-handle, and renderer orchestration use their real code.
These tests do not measure GPU output or rendering performance.
"""

from __future__ import annotations

import importlib
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from examples.cli import EXAMPLES
from plyunit.backends.integrations.raylib import handler


@pytest.fixture
def example_backend(monkeypatch):
    """Supply native resource structs and a two-frame window without a GPU."""
    import pyray as pr
    import plyunit._bootstrap as bootstrap
    from plyunit.backends.integrations import raylib
    from plyunit.backends.integrations.raylib import assets, camera2d, shader, text, window
    from plyunit.backends.integrations.raylib.input import gamepad, input as input_module, mouse, touch
    from plyunit.backends.integrations.raylib.renderer import canvas
    from plyunit.core.app import App
    from plyunit.core.units import unit as unit_module
    from plyunit.core.units.unit_registry import UnitRegistry

    monkeypatch.setattr(unit_module, "units", UnitRegistry())
    state = SimpleNamespace(width=800, height=600, frames=0, next_id=100)
    fake = MagicMock()
    fake.BLACK = (0, 0, 0, 255)
    fake.WHITE = (255, 255, 255, 255)
    fake.BLANK = (0, 0, 0, 0)
    fake.KeyboardKey = pr.KeyboardKey
    fake.MouseCursor = pr.MouseCursor
    fake.Color.side_effect = lambda r, g, b, a: SimpleNamespace(r=r, g=g, b=b, a=a)
    fake.Vector2.side_effect = lambda x=0, y=0: SimpleNamespace(x=x, y=y)
    fake.Rectangle.side_effect = lambda x=0, y=0, width=0, height=0: SimpleNamespace(x=x, y=y, width=width, height=height)
    fake.Camera2D.side_effect = lambda: SimpleNamespace(offset=None, target=None, rotation=0, zoom=1)
    fake.ffi.typeof.side_effect = TypeError("fake native struct")

    def texture(width, height):
        state.next_id += 1
        return SimpleNamespace(id=state.next_id, width=width, height=height, format=7, mipmaps=1)

    def image(width, height):
        return SimpleNamespace(width=width, height=height, format=7, mipmaps=1, data=b"pixels")

    def load_image(path):
        data = Path(path).read_bytes()
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack(">II", data[16:24])
            return image(width, height)
        return image(64, 64)

    def init_window(width, height, title):
        state.width, state.height, state.frames = width, height, 0

    def should_close():
        state.frames += 1
        return state.frames > 2

    fake.init_window.side_effect = init_window
    fake.window_should_close.side_effect = should_close
    fake.get_screen_width.side_effect = lambda: state.width
    fake.get_screen_height.side_effect = lambda: state.height
    fake.get_render_width.side_effect = lambda: state.width
    fake.get_render_height.side_effect = lambda: state.height
    fake.get_frame_time.return_value = 1 / 60
    fake.get_fps.return_value = 60
    fake.is_window_resized.return_value = False
    fake.get_mouse_position.side_effect = lambda: SimpleNamespace(x=0, y=0)
    fake.get_mouse_delta.side_effect = lambda: SimpleNamespace(x=0, y=0)
    fake.get_mouse_wheel_move.return_value = 0
    fake.get_touch_point_count.return_value = 0
    fake.is_gamepad_available.return_value = False
    for name in ("is_key_pressed", "is_key_down", "is_key_released", "is_key_pressed_repeat",
        "is_mouse_button_pressed", "is_mouse_button_down", "is_mouse_button_released"):
        getattr(fake, name).return_value = False
    fake.get_world_to_screen_2d.side_effect = lambda point, camera: point
    fake.get_screen_to_world_2d.side_effect = lambda point, camera: point
    fake.load_image.side_effect = load_image
    fake.gen_image_color.side_effect = lambda width, height, color: image(width, height)
    fake.gen_image_checked.side_effect = lambda width, height, *args: image(width, height)
    fake.load_texture.side_effect = lambda path: texture(32, 32)
    fake.load_texture_from_image.side_effect = lambda value: texture(value.width, value.height)
    fake.load_image_from_texture.side_effect = lambda value: image(value.width, value.height)
    fake.load_render_texture.side_effect = lambda width, height: SimpleNamespace(id=10, texture=texture(width, height))
    fake.is_image_valid.return_value = True
    fake.is_texture_valid.return_value = True
    fake.image_format.side_effect = lambda value, format_id: setattr(value, "format", format_id)
    fake.image_resize.side_effect = lambda value, width, height: (setattr(value, "width", width), setattr(value, "height", height))
    fake.image_resize_nn.side_effect = fake.image_resize.side_effect
    fake.image_crop.side_effect = lambda value, rect: (setattr(value, "width", int(rect.width)), setattr(value, "height", int(rect.height)))
    fake.image_copy.side_effect = lambda value: image(value.width, value.height)
    fake.get_image_alpha_border.side_effect = lambda value, threshold: fake.Rectangle(0, 0, value.width, value.height)
    fake.get_image_color.return_value = SimpleNamespace(r=255, g=255, b=255, a=255)
    raw_font = SimpleNamespace(baseSize=16, glyphCount=1, glyphPadding=0,
        texture=texture(64, 64),
        recs=[SimpleNamespace(x=0, y=0, width=8, height=16)],
        glyphs=[SimpleNamespace(offsetX=0, offsetY=0, advanceX=8)])
    fake.get_font_default.return_value = raw_font
    fake.gui_get_font.return_value = raw_font
    fake.load_font.side_effect = lambda path: SimpleNamespace(
        baseSize=16, glyphCount=1, glyphPadding=0, texture=texture(64, 64),
        recs=raw_font.recs, glyphs=raw_font.glyphs)
    fake.is_font_valid.return_value = True
    fake.get_glyph_index.return_value = 0
    fake.load_shader_from_memory.side_effect = lambda *args: SimpleNamespace(id=200)
    fake.load_shader.side_effect = lambda *args: SimpleNamespace(id=200)
    fake.is_shader_valid.return_value = True
    fake.rl_get_shader_id_default.return_value = 1
    fake.get_shader_location.return_value = 1
    fake.ffi.new.side_effect = lambda signature, values=None: list(values or [])
    modules = (assets, camera2d, handler, shader, text, window, gamepad, input_module, mouse, touch, canvas)
    for module in modules:
        monkeypatch.setattr(module, "pr", fake)
    monkeypatch.setitem(__import__("sys").modules, "pyray", fake)
    canvas._cache_color.clear()
    monkeypatch.setattr(App, "setup_logging", lambda *args: None)
    monkeypatch.setattr(canvas, "init_stencil", lambda: True)
    for name in ("begin_stencil_mask", "end_stencil_mask", "end_stencil_mask_inverse", "end_stencil_mode"):
        monkeypatch.setattr(canvas, name, lambda *args: None)
    stream = SimpleNamespace(texture=handler.Texture2D.from_raw(texture(800, 480)), update=lambda pixels: True)
    monkeypatch.setattr(canvas, "init_streaming", lambda: True)
    monkeypatch.setattr(canvas, "create_streaming_texture", lambda *args, **kwargs: stream)
    monkeypatch.setattr(canvas, "destroy_streaming_texture", lambda value: None)

    class Batch:
        capacity = 16384

        def init(self, max_sprites):
            self.capacity = max_sprites

        def shutdown(self):
            pass

        def texture_id(self, handle):
            assert isinstance(handle, handler.Texture2D)
            return int(handle.raw_texture.id)

        def submit_frame(self, **kwargs):
            pass

    factories = {name: getattr(raylib, name) for name in (
        "Window", "Canvas2D", "Assets", "Camera2D", "Audio")}
    factories["UnifiedBufferBatch"] = Batch
    monkeypatch.setattr(bootstrap, "_load_backend_bindings", lambda: factories)
    if importlib.util.find_spec("imgui_bundle") is not None:
        from plyunit.backends.imgui.raylib.service import ImGui
        from plyunit.backends.imgui.raylib.backend import ImGuiBackend

        monkeypatch.setattr(ImGuiBackend, "setup", lambda *args, **kwargs: None)
        monkeypatch.setattr(ImGuiBackend, "shutdown", lambda *args: None)
        monkeypatch.setattr(ImGui, "frame", lambda *args: None)
    return fake


@pytest.mark.parametrize("name,target", EXAMPLES.items())
def test_example_main_completes_two_frames(name, target, example_backend) -> None:
    """Exercise construction, loading, scene submission, and cleanup."""
    if name == "imgui":
        pytest.importorskip("imgui_bundle")
    module_name, entry = target.split(":", 1)
    module = importlib.import_module(module_name)
    getattr(module, entry)()
    example_backend.close_window.assert_called_once()

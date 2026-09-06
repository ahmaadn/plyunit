from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_raylib_imgui_backend_setup_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("imgui_bundle")
    pytest.importorskip("OpenGL")

    import plyunit.backends.imgui.raylib.backend as backend_mod
    from plyunit.backends.imgui.raylib.backend import ImGuiBackend

    fake_io = SimpleNamespace(
        backend_flags=0,
        display_size=None,
        display_framebuffer_scale=None,
        delta_time=0.0,
        want_capture_mouse=False,
        want_capture_keyboard=False,
        want_set_mouse_pos=False,
        set_ini_filename=lambda path: None,
        add_focus_event=lambda *a: None,
        add_key_event=lambda *a: None,
        add_input_character=lambda *a: None,
        add_mouse_pos_event=lambda *a: None,
        add_mouse_button_event=lambda *a: None,
        add_mouse_wheel_event=lambda *a: None,
    )
    fake_ctx = object()
    fake_draw = object()

    events: list[str] = []

    class FakeImGui:
        BackendFlags_ = SimpleNamespace(has_mouse_cursors=1, has_set_mouse_pos=2)
        MouseButton_ = SimpleNamespace(left=0, right=1, middle=2)
        Key = SimpleNamespace(
            mod_ctrl=100,
            mod_shift=101,
            mod_alt=102,
            mod_super=103,
            tab=1,
        )
        Cond_ = SimpleNamespace(always=1)
        WindowFlags_ = SimpleNamespace()

        @staticmethod
        def create_context():
            events.append("create_context")
            return fake_ctx

        @staticmethod
        def set_current_context(ctx):
            events.append("set_ctx")

        @staticmethod
        def destroy_context(ctx):
            events.append("destroy")

        @staticmethod
        def style_colors_dark():
            events.append("dark")

        @staticmethod
        def style_colors_light():
            events.append("light")

        @staticmethod
        def get_io():
            return fake_io

        @staticmethod
        def ImVec2(x, y):
            return (x, y)

        @staticmethod
        def new_frame():
            events.append("new_frame")

        @staticmethod
        def begin(title):
            events.append(f"begin:{title}")

        @staticmethod
        def text(t):
            events.append(f"text:{t}")

        @staticmethod
        def end():
            events.append("end")

        @staticmethod
        def render():
            events.append("render")

        @staticmethod
        def get_draw_data():
            return fake_draw

    class FakeProg:
        def __init__(self):
            events.append("prog_init")
            self.io = fake_io
            self.shutdown = lambda: events.append("prog_shutdown")
            self.render = lambda dd: events.append(f"prog_render:{dd is fake_draw}")
            self._update_textures = lambda: events.append("prog_textures")

    monkeypatch.setattr(backend_mod, "imgui", FakeImGui)
    monkeypatch.setattr(backend_mod, "ProgrammablePipelineRenderer", FakeProg)

    fake_pr = SimpleNamespace(
        is_window_focused=lambda: True,
        get_screen_width=lambda: 640,
        get_screen_height=lambda: 360,
        get_render_width=lambda: 640,
        get_render_height=lambda: 360,
        get_frame_time=lambda: 0.016,
        begin_drawing=lambda: events.append("begin_drawing"),
        end_drawing=lambda: events.append("end_drawing"),
        rl_draw_render_batch_active=lambda: events.append("flush"),
        rl_set_texture=lambda tid: events.append(f"tex:{tid}"),
        is_key_down=lambda k: False,
        is_key_pressed=lambda k: False,
        is_key_released=lambda k: False,
        get_char_pressed=lambda: 0,
        get_mouse_x=lambda: 10,
        get_mouse_y=lambda: 20,
        is_mouse_button_pressed=lambda b: False,
        is_mouse_button_released=lambda b: False,
        get_mouse_wheel_move_v=lambda: SimpleNamespace(x=0.0, y=0.0),
        MouseButton=SimpleNamespace(
            MOUSE_BUTTON_LEFT=0,
            MOUSE_BUTTON_RIGHT=1,
            MOUSE_BUTTON_MIDDLE=2,
        ),
    )
    # Expand KEY_MAP safely: any missing attr returns 0
    class _KeyNS:
        def __getattr__(self, name):
            return 0

    fake_pr.KeyboardKey = _KeyNS()
    monkeypatch.setattr(backend_mod, "pr", fake_pr)
    # KEY_MAP is built at import from real pyray; rebuild empty for unit test
    monkeypatch.setattr(backend_mod, "_KEY_MAP", [])

    b = ImGuiBackend()
    b.setup(dark_style=True, no_ini=True)
    assert b.context is fake_ctx
    assert "create_context" in events
    assert "prog_init" in events
    assert fake_io.backend_flags != 0

    b.new_frame(0.02)
    assert fake_io.delta_time == 0.02
    assert "new_frame" in events

    b.render()
    assert "render" in events
    assert any(e.startswith("prog_render") for e in events)

    assert b.want_capture_mouse() is False
    assert b.want_capture_keyboard() is False

    b.shutdown()
    assert "destroy" in events
    assert b.context is None


def test_raylib_imgui_backend_light_style(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("imgui_bundle")
    pytest.importorskip("OpenGL")

    import plyunit.backends.imgui.raylib.backend as backend_mod
    from plyunit.backends.imgui.raylib.backend import ImGuiBackend

    styles: list[str] = []
    fake_io = SimpleNamespace(
        backend_flags=0,
        display_size=None,
        display_framebuffer_scale=None,
        delta_time=0.0,
        want_capture_mouse=False,
        want_capture_keyboard=False,
        want_set_mouse_pos=False,
        set_ini_filename=lambda path: None,
    )

    class FakeImGui:
        BackendFlags_ = SimpleNamespace(has_mouse_cursors=1, has_set_mouse_pos=2)

        @staticmethod
        def create_context():
            return object()

        @staticmethod
        def set_current_context(ctx):
            pass

        @staticmethod
        def destroy_context(ctx):
            pass

        @staticmethod
        def style_colors_dark():
            styles.append("dark")

        @staticmethod
        def style_colors_light():
            styles.append("light")

        @staticmethod
        def get_io():
            return fake_io

        @staticmethod
        def ImVec2(x, y):
            return (x, y)

        @staticmethod
        def new_frame():
            pass

        @staticmethod
        def begin(t):
            pass

        @staticmethod
        def text(t):
            pass

        @staticmethod
        def end():
            pass

        @staticmethod
        def render():
            pass

        @staticmethod
        def get_draw_data():
            return object()

    class FakeProg:
        def __init__(self):
            self.io = fake_io
            self.shutdown = lambda: None
            self.render = lambda dd: None
            self._update_textures = lambda: None

    monkeypatch.setattr(backend_mod, "imgui", FakeImGui)
    monkeypatch.setattr(backend_mod, "ProgrammablePipelineRenderer", FakeProg)
    monkeypatch.setattr(
        backend_mod,
        "pr",
        SimpleNamespace(
            is_window_focused=lambda: True,
            get_screen_width=lambda: 100,
            get_screen_height=lambda: 100,
            get_render_width=lambda: 100,
            get_render_height=lambda: 100,
            get_frame_time=lambda: 0.016,
            begin_drawing=lambda: None,
            end_drawing=lambda: None,
            rl_draw_render_batch_active=lambda: None,
            rl_set_texture=lambda t: None,
        ),
    )
    monkeypatch.setattr(backend_mod, "_KEY_MAP", [])

    b = ImGuiBackend()
    b.setup(dark_style=False, no_ini=False)
    assert styles == ["light"]
    b.shutdown()

"""Raylib + Dear ImGui backend (imgui-bundle).

The architecture follows ``imp/backend.py`` + ``imp/zengl_renderer.py``:

- Input: raylib → ``ImGuiIO`` (same mapping as rlImGui / imp).
- Render: ``ProgrammablePipelineRenderer`` (bulk OpenGL VBO upload +
  ``glDrawElements``) — **not** per-vertex ``rl_vertex*`` calls from
  Python.

Texture upload uses imgui_bundle's official OpenGL path
(``glTexImage2D`` / ``glTexSubImage2D``), which is reliable with the
shared raylib GL context.

Requires the **imgui** extra (imgui-bundle, PyOpenGL):
``uv sync --package plyunit --extra raylib --extra imgui`` in the monorepo
workspace.
"""

from __future__ import annotations

from typing import Any

import pyray as pr
from imgui_bundle import imgui
from imgui_bundle.python_backends.opengl_backend_programmable import (
    ProgrammablePipelineRenderer,
)

_KEY_MAP: list[tuple[int, imgui.Key]] = [
    (pr.KeyboardKey.KEY_TAB, imgui.Key.tab),
    (pr.KeyboardKey.KEY_LEFT, imgui.Key.left_arrow),
    (pr.KeyboardKey.KEY_RIGHT, imgui.Key.right_arrow),
    (pr.KeyboardKey.KEY_UP, imgui.Key.up_arrow),
    (pr.KeyboardKey.KEY_DOWN, imgui.Key.down_arrow),
    (pr.KeyboardKey.KEY_PAGE_UP, imgui.Key.page_up),
    (pr.KeyboardKey.KEY_PAGE_DOWN, imgui.Key.page_down),
    (pr.KeyboardKey.KEY_HOME, imgui.Key.home),
    (pr.KeyboardKey.KEY_END, imgui.Key.end),
    (pr.KeyboardKey.KEY_INSERT, imgui.Key.insert),
    (pr.KeyboardKey.KEY_DELETE, imgui.Key.delete),
    (pr.KeyboardKey.KEY_BACKSPACE, imgui.Key.backspace),
    (pr.KeyboardKey.KEY_SPACE, imgui.Key.space),
    (pr.KeyboardKey.KEY_ENTER, imgui.Key.enter),
    (pr.KeyboardKey.KEY_ESCAPE, imgui.Key.escape),
    (pr.KeyboardKey.KEY_APOSTROPHE, imgui.Key.apostrophe),
    (pr.KeyboardKey.KEY_COMMA, imgui.Key.comma),
    (pr.KeyboardKey.KEY_MINUS, imgui.Key.minus),
    (pr.KeyboardKey.KEY_PERIOD, imgui.Key.period),
    (pr.KeyboardKey.KEY_SLASH, imgui.Key.slash),
    (pr.KeyboardKey.KEY_SEMICOLON, imgui.Key.semicolon),
    (pr.KeyboardKey.KEY_EQUAL, imgui.Key.equal),
    (pr.KeyboardKey.KEY_LEFT_BRACKET, imgui.Key.left_bracket),
    (pr.KeyboardKey.KEY_BACKSLASH, imgui.Key.backslash),
    (pr.KeyboardKey.KEY_RIGHT_BRACKET, imgui.Key.right_bracket),
    (pr.KeyboardKey.KEY_GRAVE, imgui.Key.grave_accent),
    (pr.KeyboardKey.KEY_CAPS_LOCK, imgui.Key.caps_lock),
    (pr.KeyboardKey.KEY_SCROLL_LOCK, imgui.Key.scroll_lock),
    (pr.KeyboardKey.KEY_NUM_LOCK, imgui.Key.num_lock),
    (pr.KeyboardKey.KEY_PRINT_SCREEN, imgui.Key.print_screen),
    (pr.KeyboardKey.KEY_PAUSE, imgui.Key.pause),
    (pr.KeyboardKey.KEY_KP_0, imgui.Key.keypad0),
    (pr.KeyboardKey.KEY_KP_1, imgui.Key.keypad1),
    (pr.KeyboardKey.KEY_KP_2, imgui.Key.keypad2),
    (pr.KeyboardKey.KEY_KP_3, imgui.Key.keypad3),
    (pr.KeyboardKey.KEY_KP_4, imgui.Key.keypad4),
    (pr.KeyboardKey.KEY_KP_5, imgui.Key.keypad5),
    (pr.KeyboardKey.KEY_KP_6, imgui.Key.keypad6),
    (pr.KeyboardKey.KEY_KP_7, imgui.Key.keypad7),
    (pr.KeyboardKey.KEY_KP_8, imgui.Key.keypad8),
    (pr.KeyboardKey.KEY_KP_9, imgui.Key.keypad9),
    (pr.KeyboardKey.KEY_KP_DECIMAL, imgui.Key.keypad_decimal),
    (pr.KeyboardKey.KEY_KP_DIVIDE, imgui.Key.keypad_divide),
    (pr.KeyboardKey.KEY_KP_MULTIPLY, imgui.Key.keypad_multiply),
    (pr.KeyboardKey.KEY_KP_SUBTRACT, imgui.Key.keypad_subtract),
    (pr.KeyboardKey.KEY_KP_ADD, imgui.Key.keypad_add),
    (pr.KeyboardKey.KEY_KP_ENTER, imgui.Key.keypad_enter),
    (pr.KeyboardKey.KEY_KP_EQUAL, imgui.Key.keypad_equal),
    (pr.KeyboardKey.KEY_LEFT_SHIFT, imgui.Key.left_shift),
    (pr.KeyboardKey.KEY_LEFT_CONTROL, imgui.Key.left_ctrl),
    (pr.KeyboardKey.KEY_LEFT_ALT, imgui.Key.left_alt),
    (pr.KeyboardKey.KEY_LEFT_SUPER, imgui.Key.left_super),
    (pr.KeyboardKey.KEY_RIGHT_SHIFT, imgui.Key.right_shift),
    (pr.KeyboardKey.KEY_RIGHT_CONTROL, imgui.Key.right_ctrl),
    (pr.KeyboardKey.KEY_RIGHT_ALT, imgui.Key.right_alt),
    (pr.KeyboardKey.KEY_RIGHT_SUPER, imgui.Key.right_super),
    (pr.KeyboardKey.KEY_KB_MENU, imgui.Key.menu),
    (pr.KeyboardKey.KEY_ZERO, imgui.Key._0),
    (pr.KeyboardKey.KEY_ONE, imgui.Key._1),
    (pr.KeyboardKey.KEY_TWO, imgui.Key._2),
    (pr.KeyboardKey.KEY_THREE, imgui.Key._3),
    (pr.KeyboardKey.KEY_FOUR, imgui.Key._4),
    (pr.KeyboardKey.KEY_FIVE, imgui.Key._5),
    (pr.KeyboardKey.KEY_SIX, imgui.Key._6),
    (pr.KeyboardKey.KEY_SEVEN, imgui.Key._7),
    (pr.KeyboardKey.KEY_EIGHT, imgui.Key._8),
    (pr.KeyboardKey.KEY_NINE, imgui.Key._9),
    (pr.KeyboardKey.KEY_A, imgui.Key.a),
    (pr.KeyboardKey.KEY_B, imgui.Key.b),
    (pr.KeyboardKey.KEY_C, imgui.Key.c),
    (pr.KeyboardKey.KEY_D, imgui.Key.d),
    (pr.KeyboardKey.KEY_E, imgui.Key.e),
    (pr.KeyboardKey.KEY_F, imgui.Key.f),
    (pr.KeyboardKey.KEY_G, imgui.Key.g),
    (pr.KeyboardKey.KEY_H, imgui.Key.h),
    (pr.KeyboardKey.KEY_I, imgui.Key.i),
    (pr.KeyboardKey.KEY_J, imgui.Key.j),
    (pr.KeyboardKey.KEY_K, imgui.Key.k),
    (pr.KeyboardKey.KEY_L, imgui.Key.l),
    (pr.KeyboardKey.KEY_M, imgui.Key.m),
    (pr.KeyboardKey.KEY_N, imgui.Key.n),
    (pr.KeyboardKey.KEY_O, imgui.Key.o),
    (pr.KeyboardKey.KEY_P, imgui.Key.p),
    (pr.KeyboardKey.KEY_Q, imgui.Key.q),
    (pr.KeyboardKey.KEY_R, imgui.Key.r),
    (pr.KeyboardKey.KEY_S, imgui.Key.s),
    (pr.KeyboardKey.KEY_T, imgui.Key.t),
    (pr.KeyboardKey.KEY_U, imgui.Key.u),
    (pr.KeyboardKey.KEY_V, imgui.Key.v),
    (pr.KeyboardKey.KEY_W, imgui.Key.w),
    (pr.KeyboardKey.KEY_X, imgui.Key.x),
    (pr.KeyboardKey.KEY_Y, imgui.Key.y),
    (pr.KeyboardKey.KEY_Z, imgui.Key.z),
    (pr.KeyboardKey.KEY_F1, imgui.Key.f1),
    (pr.KeyboardKey.KEY_F2, imgui.Key.f2),
    (pr.KeyboardKey.KEY_F3, imgui.Key.f3),
    (pr.KeyboardKey.KEY_F4, imgui.Key.f4),
    (pr.KeyboardKey.KEY_F5, imgui.Key.f5),
    (pr.KeyboardKey.KEY_F6, imgui.Key.f6),
    (pr.KeyboardKey.KEY_F7, imgui.Key.f7),
    (pr.KeyboardKey.KEY_F8, imgui.Key.f8),
    (pr.KeyboardKey.KEY_F9, imgui.Key.f9),
    (pr.KeyboardKey.KEY_F10, imgui.Key.f10),
    (pr.KeyboardKey.KEY_F11, imgui.Key.f11),
    (pr.KeyboardKey.KEY_F12, imgui.Key.f12),
]


class ImGuiBackend:
    """ImGui backend for the active host (input + OpenGL pipeline renderer).

    Uses a generic public name (not ``Raylib*``), symmetric with
    ``AssetsLoader`` / ``AudioBackend``.

    Attributes:
        context: The ImGui context (or ``None`` before :meth:`setup`).
    """

    def __init__(self) -> None:
        """Initialize the ImGui backend (empty state until :meth:`setup` runs)."""
        self._context: Any | None = None
        self._renderer: ProgrammablePipelineRenderer | None = None
        self._last_focused: bool = True
        self._last_ctrl = False
        self._last_shift = False
        self._last_alt = False
        self._last_super = False

    @property
    def context(self) -> Any | None:
        """The active imgui_bundle context (or ``None`` before setup)."""
        return self._context

    def setup(self, *, dark_style: bool = True, no_ini: bool = True) -> None:
        """Initialize the imgui_bundle context and the OpenGL renderer.

        Args:
            dark_style: If ``True``, use the dark color palette.
            no_ini: Disable the ``.ini`` file if ``True`` (ImGui does not
                persist state).
        """
        if self._context is not None:
            return
        # GL context must already exist (raylib window initialized).
        self._context = imgui.create_context()
        imgui.set_current_context(self._context)
        if dark_style:
            imgui.style_colors_dark()
        else:
            imgui.style_colors_light()
        # Creates GL objects + sets RendererHasTextures (official path).
        self._renderer = ProgrammablePipelineRenderer()
        io = imgui.get_io()
        if no_ini:
            io.set_ini_filename("")
        io.backend_flags |= int(imgui.BackendFlags_.has_mouse_cursors)
        io.backend_flags |= int(imgui.BackendFlags_.has_set_mouse_pos)
        self._last_focused = bool(pr.is_window_focused())
        # Warmup with a real draw so font atlas is uploaded and the first
        # visible app frame is not a black panel (ImGui 1.92 texture model).
        io.display_size = imgui.ImVec2(
            float(max(pr.get_screen_width(), 1)),
            float(max(pr.get_screen_height(), 1)),
        )
        io.display_framebuffer_scale = imgui.ImVec2(1.0, 1.0)
        io.delta_time = 1.0 / 60.0
        # Comment out the two-frame warmup drawing sequence that was previously
        # executed during initialization, as it is no longer needed and may
        # cause unintended side effects during backend setup.
        # for _ in range(2):
        #     pr.begin_drawing()
        #     imgui.new_frame()
        #     imgui.begin("##plyunit_imgui_warmup")
        #     imgui.text(".")
        #     imgui.end()
        #     imgui.render()
        #     pr.rl_draw_render_batch_active()
        #     self._renderer.render(imgui.get_draw_data())
        #     pr.rl_set_texture(0)
        #     pr.end_drawing()

    def shutdown(self) -> None:
        """Destroy the ImGui context and clean up the OpenGL renderer resources."""
        if self._context is None:
            return
        imgui.set_current_context(self._context)
        if self._renderer is not None:
            self._renderer.shutdown()
            self._renderer = None
        imgui.destroy_context(self._context)
        self._context = None

    def new_frame(self, delta_time: float | None = None) -> None:
        """Start a new ImGui frame and feed input events from raylib.

        Args:
            delta_time: Inter-frame delta time (seconds). ``None`` = use
            ``pr.get_frame_time()``.

        Raises:
            RuntimeError: If :meth:`setup` has not been called.
        """
        if self._context is None or self._renderer is None:
            raise RuntimeError("ImGuiBackend.setup() must be called first")
        imgui.set_current_context(self._context)
        io = self._renderer.io
        io.display_size = imgui.ImVec2(
            float(pr.get_screen_width()),
            float(pr.get_screen_height()),
        )
        # raylib render size may differ under HiDPI; scale like imp/backend.
        fb_w = float(pr.get_render_width())
        fb_h = float(pr.get_render_height())
        sw = max(float(pr.get_screen_width()), 1.0)
        sh = max(float(pr.get_screen_height()), 1.0)
        io.display_framebuffer_scale = imgui.ImVec2(fb_w / sw, fb_h / sh)
        dt = float(delta_time) if delta_time is not None else float(pr.get_frame_time())
        io.delta_time = dt if dt > 0.0 else 0.001
        self._process_events(io)
        imgui.new_frame()

    def render(self) -> None:
        """Render ImGui draw data using the programmable OpenGL pipeline."""
        if self._context is None or self._renderer is None:
            return
        imgui.set_current_context(self._context)
        imgui.render()
        # Flush any pending raylib/rlgl batch before custom OpenGL state.
        pr.rl_draw_render_batch_active()
        self._renderer.render(imgui.get_draw_data())
        # Restore rlgl default texture binding after foreign GL work.
        pr.rl_set_texture(0)
        pr.rl_draw_render_batch_active()

    def want_capture_mouse(self) -> bool:
        """Return ``True`` if ImGui wants to capture mouse events.

        Returns:
            ``True`` if the context is active and ImGui currently wants
            the mouse.
        """
        if self._context is None:
            return False
        imgui.set_current_context(self._context)
        return bool(imgui.get_io().want_capture_mouse)

    def want_capture_keyboard(self) -> bool:
        """Return ``True`` if ImGui wants to capture keyboard events.

        Returns:
            ``True`` if the context is active and ImGui currently wants
            the keyboard.
        """
        if self._context is None:
            return False
        imgui.set_current_context(self._context)
        return bool(imgui.get_io().want_capture_keyboard)

    def _process_events(self, io: imgui.IO) -> None:
        """Bridge raylib events (keyboard/mouse/wheel/focus) to ImGui IO.

        Args:
            io: The active ``imgui.IO`` object.
        """
        focused = bool(pr.is_window_focused())
        if focused != self._last_focused:
            io.add_focus_event(focused)
            self._last_focused = focused

        ctrl = pr.is_key_down(pr.KeyboardKey.KEY_LEFT_CONTROL) or pr.is_key_down(
            pr.KeyboardKey.KEY_RIGHT_CONTROL
        )
        shift = pr.is_key_down(pr.KeyboardKey.KEY_LEFT_SHIFT) or pr.is_key_down(
            pr.KeyboardKey.KEY_RIGHT_SHIFT
        )
        alt = pr.is_key_down(pr.KeyboardKey.KEY_LEFT_ALT) or pr.is_key_down(
            pr.KeyboardKey.KEY_RIGHT_ALT
        )
        super_key = pr.is_key_down(pr.KeyboardKey.KEY_LEFT_SUPER) or pr.is_key_down(
            pr.KeyboardKey.KEY_RIGHT_SUPER
        )
        if ctrl != self._last_ctrl:
            io.add_key_event(imgui.Key.mod_ctrl, ctrl)
            self._last_ctrl = ctrl
        if shift != self._last_shift:
            io.add_key_event(imgui.Key.mod_shift, shift)
            self._last_shift = shift
        if alt != self._last_alt:
            io.add_key_event(imgui.Key.mod_alt, alt)
            self._last_alt = alt
        if super_key != self._last_super:
            io.add_key_event(imgui.Key.mod_super, super_key)
            self._last_super = super_key

        for ray_key, im_key in _KEY_MAP:
            if pr.is_key_pressed(ray_key):
                io.add_key_event(im_key, True)
            elif pr.is_key_released(ray_key):
                io.add_key_event(im_key, False)

        if io.want_capture_keyboard:
            codepoint = pr.get_char_pressed()
            while codepoint != 0:
                io.add_input_character(codepoint)
                codepoint = pr.get_char_pressed()

        if focused:
            if not io.want_set_mouse_pos:
                io.add_mouse_pos_event(float(pr.get_mouse_x()), float(pr.get_mouse_y()))
            for ray_btn, im_btn in (
                (pr.MouseButton.MOUSE_BUTTON_LEFT, int(imgui.MouseButton_.left)),
                (pr.MouseButton.MOUSE_BUTTON_RIGHT, int(imgui.MouseButton_.right)),
                (pr.MouseButton.MOUSE_BUTTON_MIDDLE, int(imgui.MouseButton_.middle)),
            ):
                if pr.is_mouse_button_pressed(ray_btn):
                    io.add_mouse_button_event(im_btn, True)
                elif pr.is_mouse_button_released(ray_btn):
                    io.add_mouse_button_event(im_btn, False)
            wheel = pr.get_mouse_wheel_move_v()
            io.add_mouse_wheel_event(float(wheel.x), float(wheel.y))


__all__ = ["ImGuiBackend"]

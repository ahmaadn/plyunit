"""ImGui — optional immediate-mode UI service for plyunit.

Single service that owns both the Dear ImGui context (imgui-bundle) and the
raylib integration (input bridge + OpenGL pipeline renderer). It implements
:class:`plyunit.backends.ports.imgui.ImGuiPort` structurally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyray as pr
from imgui_bundle import imgui
from imgui_bundle.python_backends.opengl_backend_programmable import (
    ProgrammablePipelineRenderer,
)

from plyunit.core.units.service_unit import ServiceUnit

if TYPE_CHECKING:
    from plyunit.backends.ports.imgui import DrawCallback
    from plyunit.core.app import App


__all__ = ("ImGui",)


_FALLBACK_DELTA_TIME = 0.001
_SETUP_DELTA_TIME = 1.0 / 60.0

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

# (imgui modifier key, (raylib left key, raylib right key))
_MODIFIER_MAP: tuple[tuple[imgui.Key, tuple[int, int]], ...] = (
    (
        imgui.Key.mod_ctrl,
        (pr.KeyboardKey.KEY_LEFT_CONTROL, pr.KeyboardKey.KEY_RIGHT_CONTROL),
    ),
    (
        imgui.Key.mod_shift,
        (pr.KeyboardKey.KEY_LEFT_SHIFT, pr.KeyboardKey.KEY_RIGHT_SHIFT),
    ),
    (
        imgui.Key.mod_alt,
        (pr.KeyboardKey.KEY_LEFT_ALT, pr.KeyboardKey.KEY_RIGHT_ALT),
    ),
    (
        imgui.Key.mod_super,
        (pr.KeyboardKey.KEY_LEFT_SUPER, pr.KeyboardKey.KEY_RIGHT_SUPER),
    ),
)

_MOUSE_BUTTON_MAP: tuple[tuple[int, int], ...] = (
    (pr.MouseButton.MOUSE_BUTTON_LEFT, int(imgui.MouseButton_.left)),
    (pr.MouseButton.MOUSE_BUTTON_RIGHT, int(imgui.MouseButton_.right)),
    (pr.MouseButton.MOUSE_BUTTON_MIDDLE, int(imgui.MouseButton_.middle)),
)


class ImGui(ServiceUnit):
    """Optional ImGui service hooked into the App render frame.

    Implements ``ImGuiPort`` structurally: it owns the ImGui context, the
    raylib → ImGui input bridge and the OpenGL pipeline renderer.

    Attributes:
        context: The ImGui context (or ``None`` before attach).
        active: ``True`` once the ImGui context is set up and attached to
            the App.
    """

    def __init__(self, *, dark_style: bool = True, no_ini: bool = True) -> None:
        """Initialize the ImGui service (empty state until attached).

        Args:
            dark_style: Apply the dark theme to ImGui.
            no_ini: Disable the ``.ini`` file so ImGui does not persist state.
        """
        super().__init__(name="ImGui", tags={"service", "imgui", "ui"})
        self._dark_style = dark_style
        self._no_ini = no_ini
        self._draw_callbacks: list[DrawCallback] = []
        self._app: App | None = None
        self._active = False
        self._context: Any | None = None
        self._renderer: ProgrammablePipelineRenderer | None = None
        self._last_focused = True
        self._modifier_state: list[bool] = [False] * len(_MODIFIER_MAP)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def context(self) -> Any | None:
        """The active imgui_bundle context (or ``None`` before attach)."""
        return self._context

    @property
    def active(self) -> bool:
        """``True`` while the service is attached and active."""
        return self._active

    # ------------------------------------------------------------------
    # Panel callbacks (ImGuiPort)
    # ------------------------------------------------------------------

    def add_draw(self, callback: DrawCallback) -> None:
        """Register an additional ImGui panel callback (called after NewFrame).

        Args:
            callback: Argument-less callable that draws a panel.
        """
        if callback not in self._draw_callbacks:
            self._draw_callbacks.append(callback)

    def remove_draw(self, callback: DrawCallback) -> None:
        """Remove a registered ImGui panel callback.

        Args:
            callback: Callable to remove (silent no-op if absent).
        """
        try:
            self._draw_callbacks.remove(callback)
        except ValueError:
            return

    def set_draw(self, callback: DrawCallback | None) -> None:
        """Replace the whole callback list with a single callback (or clear it).

        Args:
            callback: A single callback, or ``None`` to empty the list.
        """
        self._draw_callbacks.clear()
        if callback is not None:
            self._draw_callbacks.append(callback)

    def clear_draw(self) -> None:
        """Remove all ImGui panel callbacks."""
        self._draw_callbacks.clear()

    # ------------------------------------------------------------------
    # Input capture queries (ImGuiPort)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def on_attach(self, app: App) -> None:
        """Registry hook — set up the ImGui context and OpenGL renderer.

        Args:
            app: The ``App`` instance receiving this service.
        """
        self._app = app
        self._create_context()
        self._active = True

    def on_detach(self, app: App) -> None:
        """Detach the service from the ``App`` before the window closes.

        Args:
            app: The ``App`` instance this service is being detached from.
        """
        self._destroy_context()
        self._active = False
        self._app = None

    # ------------------------------------------------------------------
    # Frame (ImGuiPort)
    # ------------------------------------------------------------------

    def frame(self, dt: float | None = None) -> None:
        """Run one ImGui frame: NewFrame → draw callbacks → Render.

        Called manually by the user from ``App.update(dt)``, after
        ``renderer.flush_all(...)`` and before ``window.end_drawing()`` so
        ImGui draws on top of the game while still inside the drawing block.

        Args:
            dt: Frame delta time in seconds. ``None`` falls back to
                ``app.window.dt`` (or ``0.0`` when no window is available).
        """
        if not self._active:
            return
        self._begin_frame(self._default_dt() if dt is None else dt)
        for callback in list(self._draw_callbacks):
            callback()
        self._render()

    def _default_dt(self) -> float:
        """Return ``app.window.dt``, or ``0.0`` when no window is available."""
        if self._app is None or self._app.window is None:
            return 0.0
        return float(self._app.window.dt)

    # ------------------------------------------------------------------
    # Context + renderer management
    # ------------------------------------------------------------------

    def _create_context(self) -> None:
        """Create the imgui_bundle context and the OpenGL renderer.

        The GL context must already exist (raylib window initialized).
        Does nothing if the context was already created.
        """
        if self._context is not None:
            return
        self._context = imgui.create_context()
        imgui.set_current_context(self._context)
        if self._dark_style:
            imgui.style_colors_dark()
        else:
            imgui.style_colors_light()
        # Creates GL objects + sets RendererHasTextures (official path).
        self._renderer = ProgrammablePipelineRenderer()
        self._configure_io(imgui.get_io())
        self._last_focused = bool(pr.is_window_focused())

    def _configure_io(self, io: imgui.IO) -> None:
        """Set backend flags, ini persistence and initial display metrics.

        Args:
            io: The active ``imgui.IO`` object.
        """
        if self._no_ini:
            io.set_ini_filename("")
        io.backend_flags |= int(imgui.BackendFlags_.has_mouse_cursors)
        io.backend_flags |= int(imgui.BackendFlags_.has_set_mouse_pos)
        io.display_size = imgui.ImVec2(
            float(max(pr.get_screen_width(), 1)),
            float(max(pr.get_screen_height(), 1)),
        )
        io.display_framebuffer_scale = imgui.ImVec2(1.0, 1.0)
        io.delta_time = _SETUP_DELTA_TIME

    def _destroy_context(self) -> None:
        """Destroy the ImGui context and release the OpenGL renderer."""
        if self._context is None:
            return
        imgui.set_current_context(self._context)
        if self._renderer is not None:
            self._renderer.shutdown()
            self._renderer = None
        imgui.destroy_context(self._context)
        self._context = None

    # ------------------------------------------------------------------
    # Per-frame internals
    # ------------------------------------------------------------------

    def _begin_frame(self, delta_time: float) -> None:
        """Start a new ImGui frame and feed input events from raylib.

        Args:
            delta_time: Inter-frame delta time in seconds.

        Raises:
            RuntimeError: If the context has not been created yet.
        """
        if self._context is None or self._renderer is None:
            raise RuntimeError("ImGui service must be attached before frame()")
        imgui.set_current_context(self._context)
        io = self._renderer.io
        self._update_display_metrics(io)
        io.delta_time = delta_time if delta_time > 0.0 else _FALLBACK_DELTA_TIME
        self._process_events(io)
        imgui.new_frame()

    def _render(self) -> None:
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

    @staticmethod
    def _update_display_metrics(io: imgui.IO) -> None:
        """Update display size and HiDPI framebuffer scale from raylib.

        Args:
            io: The active ``imgui.IO`` object.
        """
        screen_w = float(pr.get_screen_width())
        screen_h = float(pr.get_screen_height())
        io.display_size = imgui.ImVec2(screen_w, screen_h)
        # raylib render size may differ under HiDPI; scale like imp/backend.
        io.display_framebuffer_scale = imgui.ImVec2(
            float(pr.get_render_width()) / max(screen_w, 1.0),
            float(pr.get_render_height()) / max(screen_h, 1.0),
        )

    def _process_events(self, io: imgui.IO) -> None:
        """Bridge raylib events (keyboard/mouse/wheel/focus) to ImGui IO.

        Args:
            io: The active ``imgui.IO`` object.
        """
        focused = bool(pr.is_window_focused())
        self._sync_focus(io, focused)
        self._sync_modifiers(io)
        self._sync_keys(io)
        self._sync_text(io)
        if focused:
            self._sync_mouse(io)

    def _sync_focus(self, io: imgui.IO, focused: bool) -> None:
        """Forward window focus changes to ImGui.

        Args:
            io: The active ``imgui.IO`` object.
            focused: Current raylib window focus state.
        """
        if focused == self._last_focused:
            return
        io.add_focus_event(focused)
        self._last_focused = focused

    def _sync_modifiers(self, io: imgui.IO) -> None:
        """Forward Ctrl/Shift/Alt/Super state changes to ImGui.

        Args:
            io: The active ``imgui.IO`` object.
        """
        for index, (im_key, (left, right)) in enumerate(_MODIFIER_MAP):
            down = pr.is_key_down(left) or pr.is_key_down(right)
            if down == self._modifier_state[index]:
                continue
            io.add_key_event(im_key, down)
            self._modifier_state[index] = down

    @staticmethod
    def _sync_keys(io: imgui.IO) -> None:
        """Forward key press/release events to ImGui.

        Args:
            io: The active ``imgui.IO`` object.
        """
        for ray_key, im_key in _KEY_MAP:
            if pr.is_key_pressed(ray_key):
                io.add_key_event(im_key, True)
            elif pr.is_key_released(ray_key):
                io.add_key_event(im_key, False)

    @staticmethod
    def _sync_text(io: imgui.IO) -> None:
        """Forward typed characters to ImGui while it wants the keyboard.

        Args:
            io: The active ``imgui.IO`` object.
        """
        if not io.want_capture_keyboard:
            return
        codepoint = pr.get_char_pressed()
        while codepoint != 0:
            io.add_input_character(codepoint)
            codepoint = pr.get_char_pressed()

    @staticmethod
    def _sync_mouse(io: imgui.IO) -> None:
        """Forward mouse position, buttons and wheel to ImGui.

        Args:
            io: The active ``imgui.IO`` object.
        """
        if not io.want_set_mouse_pos:
            io.add_mouse_pos_event(float(pr.get_mouse_x()), float(pr.get_mouse_y()))
        for ray_btn, im_btn in _MOUSE_BUTTON_MAP:
            if pr.is_mouse_button_pressed(ray_btn):
                io.add_mouse_button_event(im_btn, True)
            elif pr.is_mouse_button_released(ray_btn):
                io.add_mouse_button_event(im_btn, False)
        wheel = pr.get_mouse_wheel_move_v()
        io.add_mouse_wheel_event(float(wheel.x), float(wheel.y))

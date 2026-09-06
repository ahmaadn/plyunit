"""Raylib window and frame-clock service."""

from __future__ import annotations

from collections import deque

import pyray as pr

from plyunit.core.types import ColorType
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.utils import math


class Window(ServiceUnit):
    """Global window service with frame and fixed-timestep state."""

    def __init__(self) -> None:
        """Initialize the window service with neutral frame state."""
        super().__init__(name="Window", tags={"service", "window"})
        self.dt: float = 0.0
        self.unscaled_dt: float = 0.0
        self.total_time: float = 0.0
        self.frame_count: int = 0
        self.time_scale: float = 1.0
        self.fixed_delta_time: float = 1.0 / 60.0
        self.max_frame_delta_time: float = 0.25
        self.accumulator: float = 0.0
        self.alpha: float = 0.0
        self.fixed_steps: int = 0
        self._scale_before_pause: float = 1.0
        self._frame_time_samples: deque[float] = deque(maxlen=60)

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def init_window(self, width: int, height: int, title: str) -> None:
        """Open the native window.

        Args:
            width: Window width in pixels. Must be > 0.
            height: Window height in pixels. Must be > 0.
            title: Window title text.

        Raises:
            WindowAlreadyOpenError: If a window is already open.
            ValueError: If width or height is not positive.
        """
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be > 0")

        pr.init_window(int(width), int(height), title)

    def close_window(self) -> None:
        """Close the native window.

        Raises:
            WindowNotOpenError: If no window is currently open.
        """

        pr.close_window()

    def window_should_close(self) -> bool:
        """Return True if the OS or user has requested the window close."""
        return bool(pr.window_should_close())

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def set_target_fps(self, fps: int) -> None:
        """Set the target frames-per-second cap for the render loop."""
        if int(fps) <= 0:
            raise ValueError("fps must be > 0")
        pr.set_target_fps(int(fps))

    def begin_drawing(self) -> None:
        """Start a new drawing frame."""
        pr.begin_drawing()

    def end_drawing(self) -> None:
        """Finish the current drawing frame and swap buffers."""
        pr.end_drawing()

    def clear_background(self, color: ColorType) -> None:
        """Clear the backbuffer to the given color."""
        pr.clear_background(color)

    def present_loading_frame(
        self,
        color: ColorType,
        text: str | None = None,
        *,
        text_color: ColorType | None = None,
        font_size: int = 20,
    ) -> None:
        """Present one static frame, e.g. a loading screen, without the renderer.

        Useful during startup: heavy work (importing large modules, fonts,
        assets, the project) blocks the main thread so the main pipeline
        cannot draw a new frame. This static frame becomes the last
        presented image and stays visible, covering that work, until the
        main pipeline takes over.

        Args:
            color: Frame background color.
            text: Optional text centered on screen.
            text_color: Text color (default: light gray).
            font_size: Text font size.
        """
        pr.begin_drawing()
        pr.clear_background(color)
        if text:
            rgba = text_color or (200, 200, 210, 255)
            text_w = pr.measure_text(text, font_size)
            pr.draw_text(
                text,
                int((pr.get_screen_width() - text_w) * 0.5),
                int(pr.get_screen_height() * 0.5) - font_size // 2,
                font_size,
                pr.Color(rgba[0], rgba[1], rgba[2], rgba[3]),
            )
        pr.end_drawing()

    def get_frame_time(self) -> float:
        """Return the raw, unclamped delta time reported by the backend."""
        return float(pr.get_frame_time())

    def get_fps(self) -> int:
        """Return the backend-reported instantaneous FPS."""
        return int(pr.get_fps())

    @property
    def average_fps(self) -> float:
        """Return the FPS averaged over the last DEFAULT_FPS_SAMPLE_SIZE frames."""
        if not self._frame_time_samples:
            return 0.0
        mean_dt = sum(self._frame_time_samples) / len(self._frame_time_samples)
        if mean_dt <= 0.0:
            return 0.0
        return 1.0 / mean_dt

    # ------------------------------------------------------------------
    # Screen / display queries
    # ------------------------------------------------------------------

    def get_screen_width(self) -> int:
        """Return the current window width in pixels."""
        return int(pr.get_screen_width())

    def get_screen_height(self) -> int:
        """Return the current window height in pixels."""
        return int(pr.get_screen_height())

    def get_screen_size(self) -> tuple[int, int]:
        """Return the current (width, height) window size in pixels."""
        return self.get_screen_width(), self.get_screen_height()

    def set_window_size(self, width: int, height: int) -> None:
        """Resize the native window."""
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be > 0")
        pr.set_window_size(int(width), int(height))

    def set_window_title(self, title: str) -> None:
        """Change the native window title."""
        pr.set_window_title(title)

    def is_fullscreen(self) -> bool:
        """Return True if the window is currently fullscreen."""
        return bool(pr.is_window_fullscreen())

    def toggle_fullscreen(self) -> None:
        """Toggle between windowed and fullscreen mode."""
        pr.toggle_fullscreen()

    def is_focused(self) -> bool:
        """Return True if the window currently has input focus."""
        return bool(pr.is_window_focused())

    def is_resized(self) -> bool:
        """Return True if the window was resized on the last frame."""
        return bool(pr.is_window_resized())

    # ------------------------------------------------------------------
    # Frame clock / fixed timestep
    # ------------------------------------------------------------------

    def start_frame(self) -> None:
        """Capture the backend delta and advance the frame clock."""
        raw_dt = math.clamp(
            self.get_frame_time(),
            0.0,
            self.max_frame_delta_time,
        )
        self.unscaled_dt = raw_dt
        self.dt = raw_dt * self.time_scale
        self.total_time += raw_dt
        self.frame_count += 1
        self.accumulator += self.dt
        self._frame_time_samples.append(raw_dt)

    def consume_fixed_steps(self, max_steps: int) -> int:
        """Consume at most ``max_steps`` fixed updates from the accumulator.

        Args:
            max_steps: Maximum number of fixed steps to take this frame.

        Returns:
            The number of fixed steps actually consumed.

        Raises:
            ValueError: If max_steps is not > 0.
        """
        if int(max_steps) <= 0:
            raise ValueError("max_steps must be > 0")

        steps = 0
        while self.accumulator >= self.fixed_delta_time and steps < int(max_steps):
            self.accumulator -= self.fixed_delta_time
            steps += 1

        if steps == int(max_steps) and self.accumulator >= self.fixed_delta_time:
            self.accumulator = 0.0

        self.alpha = self.accumulator / self.fixed_delta_time
        self.fixed_steps += steps
        return steps

    def set_time_scale(self, value: float) -> None:
        """Set the multiplier applied to raw delta time (e.g. for slow-mo)."""
        if float(value) < 0.0:
            raise ValueError("time_scale must be >= 0")
        self.time_scale = float(value)

    def set_fixed_timestep_hz(self, hz: int) -> None:
        """Set the fixed-update rate in hertz (e.g. 60 -> 1/60s steps)."""
        if int(hz) <= 0:
            raise ValueError("fixed timestep hz must be > 0")
        self.fixed_delta_time = 1.0 / float(hz)

    @property
    def is_paused(self) -> bool:
        """Whether the frame clock is paused (time_scale == 0)."""
        return self.time_scale == 0.0

    def pause(self) -> None:
        """Pause the frame clock, remembering the current time scale."""
        if self.is_paused:
            return
        self._scale_before_pause = self.time_scale
        self.time_scale = 0.0

    def resume(self) -> None:
        """Resume the frame clock at the time scale active before pause()."""
        if not self.is_paused:
            return
        self.time_scale = self._scale_before_pause

    def reset(self) -> None:
        """Reset frame-clock state while leaving the native window untouched."""
        self.dt = 0.0
        self.unscaled_dt = 0.0
        self.total_time = 0.0
        self.frame_count = 0
        self.time_scale = 1.0
        self.accumulator = 0.0
        self.alpha = 0.0
        self.fixed_steps = 0
        self._scale_before_pause = 1.0
        self._frame_time_samples.clear()


__all__ = ["Window"]

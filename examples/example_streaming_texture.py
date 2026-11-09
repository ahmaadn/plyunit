"""Example: PBO double-buffered streaming texture (procedural noise frames).

Requires a live OpenGL context (raylib window). Demonstrates one-frame latency
upload suitable for video / webcam / CPU-generated frames.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np

import plyunit as pu

if TYPE_CHECKING:
    from plyunit.backends.ports.handler import StreamingTextureHandle


class StreamingApp(pu.App):
    _stream: StreamingTextureHandle | None = None

    def on_load(self) -> None:
        self._t0 = time.perf_counter()
        self.draw = self.renderer.draw

        if not self.canvas.init_streaming():
            raise RuntimeError("PBO streaming init failed")
        self._w, self._h = 800, 480
        self._stream = self.canvas.create_streaming_texture(
            self._w, self._h, channels=4
        )
        if self._stream is None:
            raise RuntimeError("Failed to allocate the streaming texture")
        self._frame = 0
        # Prime one frame so the first visible sample is not blank.
        self._push_frame(0.0)

    def _push_frame(self, t: float) -> None:
        stream = self._stream
        if stream is None:
            raise RuntimeError("The streaming texture is not available")
        # Cheap procedural RGBA pattern (w*h*4 bytes).
        yy, xx = np.mgrid[0 : self._h, 0 : self._w]
        phase = t * 40.0
        r = ((xx + phase) % 256).astype(np.uint8)
        g = ((yy + phase * 0.7) % 256).astype(np.uint8)
        b = (((xx + yy) * 0.5 + phase) % 256).astype(np.uint8)
        a = np.full((self._h, self._w), 255, dtype=np.uint8)
        pixels = np.dstack((r, g, b, a)).tobytes()
        if not stream.update(pixels):
            raise RuntimeError("Failed to upload a streaming texture frame")

    def fixed_update(self, dt: float, step: int) -> None:
        _ = dt, step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((12, 14, 24, 255))

        # Immediate DrawScope drawing — valid inside the drawing block.
        t = time.perf_counter() - self._t0
        self._push_frame(t)
        self._frame += 1

        stream = self._stream
        if stream is None:
            raise RuntimeError("The streaming texture is not available")
        draw = self.draw
        draw.rect((0, 0, 800, 480), (16, 18, 28, 255))
        # Scale streaming texture to window.
        draw.texture(
            texture=stream.texture,
            dest=(40, 60, 720, 360),
            tint=(255, 255, 255, 255),
        )
        draw.canvas.draw_text(
            text=f"StreamingTexture PBO  frame={self._frame}  {self._w}x{self._h}",
            pos=(12, 12),
            font_size=18,
            color=(230, 235, 255, 255),
        )

        self.renderer.flush_all()
        self.window.end_drawing()

    def on_unload(self) -> None:
        stream = self._stream
        if stream is not None:
            self.canvas.destroy_streaming_texture(stream)
            self._stream = None


def main() -> None:
    app = pu.init(
        StreamingApp(),
        pu.AppConfig(
            title="Streaming Texture Example",
            window_width=800,
            window_height=480,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()

"""Example: Input with gamepad (keyboard + pad share actions).

Controls:
- WASD / arrows or left stick / d-pad: move
- Space or face button A: jump pulse
"""

from __future__ import annotations

import pyray as pr

import plyunit as pu


class GamepadApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input(gamepad=True)
        self.touch = pu.Touch()

        self.input.map("jump", pr.KeyboardKey.KEY_SPACE, buttons=["a"])
        self.input.map_axis(
            "move_x",
            key_neg=[pr.KeyboardKey.KEY_A, pr.KeyboardKey.KEY_LEFT],
            key_pos=[pr.KeyboardKey.KEY_D, pr.KeyboardKey.KEY_RIGHT],
            pad_axis="left_x",
            pad_buttons_neg=["dpad_left"],
            pad_buttons_pos=["dpad_right"],
        )
        self.input.map_axis(
            "move_y",
            key_neg=[pr.KeyboardKey.KEY_W, pr.KeyboardKey.KEY_UP],
            key_pos=[pr.KeyboardKey.KEY_S, pr.KeyboardKey.KEY_DOWN],
            pad_axis="left_y",
            pad_buttons_neg=["dpad_up"],
            pad_buttons_pos=["dpad_down"],
        )

        self._pos = [400.0, 300.0]
        self._flash = 0.0
        self._log: list[str] = []
        self.text = pu.Text()

        pu.EventBus()
        bus = self.one("@EventBus")
        bus.subscribe("key.jump.pressed", self._on_jump)

    def _on_jump(self, **kwargs) -> None:
        _ = kwargs
        self._flash = 0.25
        self._log.append("jump")
        if len(self._log) > 6:
            self._log.pop(0)

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.input.update(dt)
        dx = self.input.get_axis("move_x")
        dy = self.input.get_axis("move_y")
        self._pos[0] += dx * 220.0 * dt
        self._pos[1] += dy * 220.0 * dt
        if self._flash > 0.0:
            self._flash = max(0.0, self._flash - dt)
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)

        x, y = self._pos
        color = (255, 220, 80, 255) if self._flash > 0 else (90, 180, 255, 255)
        self.renderer.render_rect(
            z=0,
            layer=pu.Layer.WORLD,
            rect=(x, y, 32.0, 32.0),
            color=color,
        )
        pad = self.input.gamepad
        pad_name = (
            pad.name_on_device if pad is not None and pad.is_available() else "(none)"
        )
        lines = [
            f"pad={pad_name}  touch_count={self.touch.count}",
            "move: WASD/arrows or stick/dpad  jump: Space/A",
            f"axis=({self.input.get_axis('move_x'):.2f},"
            f" {self.input.get_axis('move_y'):.2f})",
            "log: " + ", ".join(self._log),
        ]
        for i, line in enumerate(lines):
            self.text.render(
                z=0,
                layer=pu.Layer.UI,
                text=line,
                pos=(12, 12 + i * 20),
                font_size=16,
                color=(230, 235, 255, 255),
            )

        self.renderer.flush_all()
        self.window.end_drawing()


def main() -> None:
    app = pu.init(
        GamepadApp(),
        pu.AppConfig(
            title="plyunit Input + Gamepad",
            window_width=800,
            window_height=600,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()

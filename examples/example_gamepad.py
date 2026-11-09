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
        self.input = pu.Input()
        self.gamepad = pu.Gamepad()
        self.touch = pu.Touch()

        self.input.map("jump", pr.KeyboardKey.KEY_SPACE)
        self.input.map_axis(
            "move_x",
            key_neg=[pr.KeyboardKey.KEY_A, pr.KeyboardKey.KEY_LEFT],
            key_pos=[pr.KeyboardKey.KEY_D, pr.KeyboardKey.KEY_RIGHT],
        )
        self.input.map_axis(
            "move_y",
            key_neg=[pr.KeyboardKey.KEY_W, pr.KeyboardKey.KEY_UP],
            key_pos=[pr.KeyboardKey.KEY_S, pr.KeyboardKey.KEY_DOWN],
        )

        self._pos = [400.0, 300.0]
        self._flash = 0.0
        self._log: list[str] = []
        self.text = pu.Text()
        self.assets.store_texture(
            "gamepad_player",
            self.renderer.canvas.create_rect(
                rect=(0, 0, 32, 32), color=(255, 255, 255, 255)
            ),
        )
        self._player_texture = self.assets.get_asset("gamepad_player")

        self._axes = (0.0, 0.0)

    def _on_jump(self) -> None:
        self._flash = 0.25
        self._log.append("jump")
        if len(self._log) > 6:
            self._log.pop(0)

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        # Combine separate keyboard and gamepad services in application code.
        stick_x, stick_y = self.gamepad.get_vector()
        dpad_x = float(self.gamepad.is_down("dpad_right")) - float(
            self.gamepad.is_down("dpad_left")
        )
        dpad_y = float(self.gamepad.is_down("dpad_down")) - float(
            self.gamepad.is_down("dpad_up")
        )
        dx = max((self.input.get_axis("move_x"), stick_x, dpad_x), key=abs)
        dy = max((self.input.get_axis("move_y"), stick_y, dpad_y), key=abs)
        self._axes = (dx, dy)
        if self.input.is_pressed("jump") or self.gamepad.is_pressed("a"):
            self._on_jump()
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
        self.window.clear_background((245, 245, 245, 255))
        self.scene_manager.render(self.renderer)

        x, y = self._pos
        color = (255, 220, 80, 255) if self._flash > 0 else (90, 180, 255, 255)
        self.renderer.render_sprite(
            z=0,
            layer=pu.Layer.WORLD,
            texture=self._player_texture,
            pos=(x, y),
            tint=color,
        )
        pad = self.gamepad
        pad_name = pad.name_on_device if pad.is_available() else "(none)"
        lines = [
            f"pad={pad_name}  touch_count={self.touch.count}",
            "move: WASD/arrows or stick/dpad  jump: Space/A",
            f"axis=({self._axes[0]:.2f}, {self._axes[1]:.2f})",
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

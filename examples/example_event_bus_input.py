"""Example: EventBus input path (key.* / mouse.*) vs direct Input polling.

Controls:
- WASD / arrows: move (poll path still works)
- Space: jump via bus event key.jump.pressed
- Left click: bus event mouse.left.pressed
"""

from __future__ import annotations

import pyray as pr

import plyunit as pu


class EventBusInputApp(pu.App):
    def on_load(self) -> None:
        pu.EventBus()
        self.event_bus = self.one("@EventBus")

        self.input = pu.Input()
        self.mouse = pu.Mouse()

        self.input.map("move_up", pr.KeyboardKey.KEY_W, pr.KeyboardKey.KEY_UP)
        self.input.map("move_down", pr.KeyboardKey.KEY_S, pr.KeyboardKey.KEY_DOWN)
        self.input.map("move_left", pr.KeyboardKey.KEY_A, pr.KeyboardKey.KEY_LEFT)
        self.input.map("move_right", pr.KeyboardKey.KEY_D, pr.KeyboardKey.KEY_RIGHT)
        self.input.map("jump", pr.KeyboardKey.KEY_SPACE)

        self._log: list[str] = []
        self._pos = [200.0, 200.0]

        self.event_bus.subscribe(
            "key.jump.pressed",
            self._on_jump,
            priority=10,
        )
        self.event_bus.subscribe(
            "mouse.left.pressed",
            self._on_click,
            priority=0,
        )

        self.text = pu.Text()

    def _on_jump(self, **kwargs) -> None:
        self._log.append(f"bus jump action={kwargs.get('action')}")
        if len(self._log) > 8:
            self._log.pop(0)

    def _on_click(self, **kwargs) -> None:
        pos = kwargs.get("position", (0.0, 0.0))
        self._log.append(f"bus click pos={pos}")
        if len(self._log) > 8:
            self._log.pop(0)

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.input.update(dt)
        self.mouse.update(dt)
        dx = self.input.get_axis("move_left", "move_right")
        dy = self.input.get_axis("move_up", "move_down")
        self._pos[0] += dx * 180.0 * dt
        self._pos[1] += dy * 180.0 * dt
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((14, 16, 28, 255))
        self.scene_manager.render(self.renderer)

        x, y = self._pos
        self.renderer.render_rect(
            z=0,
            layer=pu.Layer.WORLD,
            rect=(x, y, 28.0, 28.0),
            color=(80, 200, 120, 255),
        )
        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text="EventBus input: Space=jump, click=mouse, WASD=poll move",
            pos=(12, 12),
            font_size=16,
            color=(230, 235, 255, 255),
        )
        for i, line in enumerate(self._log):
            self.text.render(
                z=0,
                layer=pu.Layer.UI,
                text=line,
                pos=(12, 40 + i * 18),
                font_size=14,
                color=(160, 170, 200, 255),
            )

        self.renderer.flush_all()
        self.window.end_drawing()


def main() -> None:
    app = pu.init(
        EventBusInputApp(),
        pu.AppConfig(
            title="EventBus Input Example",
            window_width=640,
            window_height=400,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()

"""Example: Timer + TweenAnimation.

- Box A: wall-clock position tween (quad_out)
- Box B: fixed-step rotation + scale parallel
- SPACE: restart sequence via generator wait
- P: pause / resume both services
"""

from __future__ import annotations

import pyray as pr

import plyunit as pu


class TweenApp(pu.App):
    def on_load(self) -> None:
        pu.Timer()
        pu.TweenAnimation()

        self.input = pu.Input()
        self.input.map("replay", pr.KeyboardKey.KEY_SPACE)
        self.input.map("pause", pr.KeyboardKey.KEY_P)

        self.box_a = pu.TransformState()
        self.box_b = pu.TransformState()
        self.box_a.set_position(80.0, 180.0)
        self.box_b.set_position(400.0, 280.0)
        self.box_b.set_scale(1.0, 1.0)
        self.box_b.set_rotation(0.0)

        self.status = "ready"
        self._paused = False
        self._start_motion()
        self.text = pu.Text()

    def _start_motion(self) -> None:
        timers = self.one("@Timer")
        tweens = self.one("@TweenAnimation")
        tweens.kill_all()
        self.box_a.set_position(80.0, 180.0)
        self.box_b.set_position(400.0, 280.0)
        self.box_b.set_scale(1.0, 1.0)
        self.box_b.set_rotation(0.0)
        self.status = "tweening"

        def seq():
            yield (
                tweens
                .to(
                    self.box_a,
                    duration=0.8,
                    easing="quad_out",
                    time_base="wall",
                )
                .position((520.0, 180.0))
                .play()
            )
            yield timers.wait(0.2, time_base="wall")
            a = tweens.to(
                self.box_b, duration=0.5, easing="back_out", time_base="fixed"
            ).rotation(360.0)
            b = tweens.to(
                self.box_b, duration=0.5, easing="quad_in_out", time_base="fixed"
            ).scale((1.8, 1.8))
            yield tweens.parallel(a, b).play()
            yield timers.wait(0.15, time_base="wall")
            yield (
                tweens
                .to(
                    self.box_a,
                    duration=0.6,
                    easing="cubic_in_out",
                    time_base="wall",
                )
                .position((80.0, 180.0))
                .play()
            )
            self.status = "done (SPACE to replay)"

        timers.run(seq())

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        if self.input.is_pressed("replay"):
            self._start_motion()
        if self.input.is_pressed("pause"):
            timers = self.one("@Timer")
            tweens = self.one("@TweenAnimation")
            self._paused = not self._paused
            if self._paused:
                timers.pause()
                tweens.pause()
                self.status = "paused"
            else:
                timers.resume()
                tweens.resume()
                self.status = "resumed"
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((14, 16, 28, 255))
        self.scene_manager.render(self.renderer)

        a = self.box_a.local
        b = self.box_b.local
        ax, ay = a.position
        bx, by = b.position
        sx, sy = b.scale
        w, h = 56.0 * sx, 56.0 * sy
        self.renderer.render_rect(
            z=0,
            layer=pu.Layer.WORLD,
            rect=(ax, ay, 48.0, 48.0),
            color=(70, 140, 255, 255),
        )
        self.renderer.render_rect(
            z=1,
            layer=pu.Layer.WORLD,
            rect=(bx - w * 0.5, by - h * 0.5, w, h),
            color=(255, 160, 60, 255),
            rotation=b.rotation,
            origin=(w * 0.5, h * 0.5),
        )
        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text="Timer + Tween demo",
            pos=(20, 16),
            font_size=22,
            color=(240, 242, 255, 255),
        )
        self.text.render(
            z=0,
            layer=pu.Layer.UI,
            text=f"Status: {self.status}  |  SPACE replay  P pause",
            pos=(20, 48),
            font_size=14,
            color=(170, 180, 210, 255),
        )

        self.renderer.flush_all()
        self.window.end_drawing()


def main() -> None:
    app = pu.init(
        TweenApp(),
        pu.AppConfig(
            title="Tween / Timer Example",
            window_width=800,
            window_height=480,
            target_fps=60,
            fixed_update_hz=60,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()

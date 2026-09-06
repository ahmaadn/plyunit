"""Example: Physics Engine Demo

Demonstrasi lengkap fitur physics engine Plyunit:
1. Physics setup dengan gravity
2. PhysicsBody dynamic (falling boxes & circles)
3. PhysicsBody kinematic (moving platform)
4. StaticBody via QuadTree (floor + walls)
5. PhysicsArea sensor (trigger zone)
6. Collision mask/layer filtering
7. PhysicsDebugDraw component (plug & play)
8. Spawning & sleeping visualization

Controls:
- Klik kiri: Spawn box
- Klik kanan: Spawn circle
- Spasi: Toggle gravity (0 ↔ 900)
- D: Toggle debug draw
- R: Reset scene
"""

import math
import random

import pyray as pr

import plyunit as pu

# ======================================================================
# Layer Constants (Godot-style bitmask bits)
# ======================================================================
LAYER_WORLD = 0  # bit 0: static geometry (floor, walls)
LAYER_PLAYER = 1  # bit 1: player objects
LAYER_ENEMY = 2  # bit 2: enemy objects
LAYER_TRIGGER = 3  # bit 3: trigger zones


# ======================================================================
# Physics Entities
# ======================================================================


class FallingBox(pu.Component):
    """Box yang jatuh dan bertabrakan."""

    def __init__(
        self, x: float, y: float, w: float = 32, h: float = 32, color_idx: int = 0
    ) -> None:
        super().__init__(name="FallingBoxRenderer")
        self.physics = pu.PhysicsBody.dynamic(mass=1.0, name="FallingBox")
        self.add_shape(pu.BoxShape(width=w, height=h, friction=0.6, elasticity=0.3))

        # Collision: berada di layer PLAYER, detect WORLD + PLAYER + ENEMY
        self.physics.filter.set_layer_bit(LAYER_PLAYER, True)
        self.physics.filter.set_mask_bit(LAYER_WORLD, True)
        self.physics.filter.set_mask_bit(LAYER_PLAYER, True)
        self.physics.filter.set_mask_bit(LAYER_ENEMY, True)

        self._colors = [
            (220, 60, 60, 255),
            (60, 160, 220, 255),
            (60, 200, 80, 255),
            (220, 180, 40, 255),
            (180, 80, 220, 255),
        ]
        self._color = self._colors[color_idx % len(self._colors)]
        self._w = w
        self._h = h
        self._spawn_pos = (x, y)

    def on_attach(self) -> None:
        self.unit.transform.set_position(*self._spawn_pos)
        self.unit.draw = self.draw
        self.unit.enable_custom_draw()
        self.unit.add_component(self.physics)

    def add_shape(self, shape: pu.PhysicsShape) -> None:
        self.physics.add_shape(shape)

    @property
    def angular_velocity(self) -> float:
        return self.physics.angular_velocity

    @angular_velocity.setter
    def angular_velocity(self, value: float) -> None:
        self.physics.angular_velocity = value

    def draw(self, canvas: pu.Canvas) -> None:
        world = self.unit.world_transform_lerp()
        hw, hh = self._w / 2, self._h / 2
        color = self._color
        if self.physics.is_sleeping:
            # Dim color saat sleeping
            color = (color[0] // 2, color[1] // 2, color[2] // 2, color[3])

        canvas.draw_rectangle(
            rect=(world.position[0], world.position[1], self._w, self._h),
            color=color,
            rotation=world.rotation,
            origin=(hw, hh),
            roundness=0.15,
        )


class FallingCircle(pu.Component):
    """Circle yang jatuh dan memantul."""

    def __init__(self, x: float, y: float, radius: float = 16) -> None:
        super().__init__(name="FallingCircleRenderer")
        self.physics = pu.PhysicsBody.dynamic(mass=0.8, name="FallingCircle")
        self.add_shape(pu.CircleShape(radius=radius, friction=0.4, elasticity=0.6))

        # Collision: berada di layer ENEMY, detect WORLD + PLAYER + ENEMY
        self.physics.filter.set_layer_bit(LAYER_ENEMY, True)
        self.physics.filter.set_mask_bit(LAYER_WORLD, True)
        self.physics.filter.set_mask_bit(LAYER_PLAYER, True)
        self.physics.filter.set_mask_bit(LAYER_ENEMY, True)

        self._radius = radius
        self._color = (
            random.randint(100, 255),
            random.randint(100, 255),
            random.randint(100, 255),
            255,
        )
        self._spawn_pos = (x, y)

    def on_attach(self) -> None:
        self.unit.transform.set_position(*self._spawn_pos)
        self.unit.draw = self.draw
        self.unit.enable_custom_draw()
        self.unit.add_component(self.physics)

    def add_shape(self, shape: pu.PhysicsShape) -> None:
        self.physics.add_shape(shape)

    @property
    def angular_velocity(self) -> float:
        return self.physics.angular_velocity

    @angular_velocity.setter
    def angular_velocity(self, value: float) -> None:
        self.physics.angular_velocity = value

    def draw(self, canvas: pu.Canvas) -> None:
        world = self.unit.world_transform_lerp()
        color = self._color
        if self.physics.is_sleeping:
            color = (color[0] // 2, color[1] // 2, color[2] // 2, color[3])

        canvas.draw_circle(
            center=world.position,
            radius=self._radius,
            color=color,
        )
        # Direction indicator
        rad = math.radians(world.rotation)
        end_x = world.position[0] + math.cos(rad) * self._radius * 0.8
        end_y = world.position[1] + math.sin(rad) * self._radius * 0.8
        canvas.draw_line(
            start=world.position,
            end=(end_x, end_y),
            color=(255, 255, 255, 180),
            thickness=2.0,
        )


class MovingPlatform(pu.Component):
    """Platform kinematic yang bergerak horizontal."""

    def __init__(self, x: float, y: float, w: float = 120, h: float = 16) -> None:
        super().__init__(name="MovingPlatformRenderer")
        self.physics = pu.PhysicsBody.kinematic(name="MovingPlatform")
        self.add_shape(pu.BoxShape(width=w, height=h, friction=0.8, elasticity=0.1))

        # Layer: WORLD agar body lain bisa landing
        self.physics.filter.set_layer_bit(LAYER_WORLD, True)
        self.physics.filter.mask = 0  # Kinematic tidak perlu detect apapun

        self._w = w
        self._h = h
        self._center_x = x
        self._time = 0.0
        self._amplitude = 120.0
        self._speed = 1.5
        self._spawn_pos = (x, y)

    def on_attach(self) -> None:
        self.unit.transform.set_position(*self._spawn_pos)
        self.unit.draw = self.draw
        self.unit.enable_custom_draw()
        self.unit.add_component(self.physics)

    def add_shape(self, shape: pu.PhysicsShape) -> None:
        self.physics.add_shape(shape)

    def update(self, dt: float) -> None:
        self._time += dt
        new_x = self._center_x + math.sin(self._time * self._speed) * self._amplitude
        self.unit.transform.set_position(new_x, self.unit.transform.local.position[1])

    def draw(self, canvas: pu.Canvas) -> None:
        world = self.unit.world_transform_lerp()
        hw, hh = self._w / 2, self._h / 2
        canvas.draw_rectangle(
            rect=(world.position[0], world.position[1], self._w, self._h),
            color=(100, 150, 255, 255),
            rotation=world.rotation,
            origin=(hw, hh),
            roundness=0.3,
        )


class TriggerZone(pu.Component):
    """Sensor zone yang mendeteksi body masuk/keluar."""

    def __init__(self, x: float, y: float, w: float = 80, h: float = 80) -> None:
        super().__init__(name="TriggerZoneRenderer")
        self.area = pu.PhysicsArea.sensor(name="TriggerZone")
        self.add_shape(pu.BoxShape(width=w, height=h))

        # Layer & mask: detect player dan enemy
        self.area.filter.set_layer_bit(LAYER_TRIGGER, True)
        self.area.filter.set_mask_bit(LAYER_PLAYER, True)
        self.area.filter.set_mask_bit(LAYER_ENEMY, True)

        self._w = w
        self._h = h
        self._body_count = 0
        self._pulse = 0.0

        self.area.on_body_entered.connect(self._on_enter)
        self.area.on_body_exited.connect(self._on_exit)
        self._spawn_pos = (x, y)

    def on_attach(self) -> None:
        self.unit.transform.set_position(*self._spawn_pos)
        self.unit.draw = self.draw
        self.unit.enable_custom_draw()
        self.unit.add_component(self.area)

    def add_shape(self, shape: pu.PhysicsShape) -> None:
        self.area.add_shape(shape)

    def _on_enter(self, body: pu.PhysicsBody) -> None:
        self._body_count += 1

    def _on_exit(self, body: pu.PhysicsBody) -> None:
        self._body_count = max(0, self._body_count - 1)

    def update(self, dt: float) -> None:
        self._pulse += dt * 3.0

    def draw(self, canvas: pu.Canvas) -> None:
        world = self.unit.world_transform_lerp()
        hw, hh = self._w / 2, self._h / 2

        # Pulse effect saat ada body di dalam
        alpha = 40
        if self._body_count > 0:
            alpha = int(40 + abs(math.sin(self._pulse)) * 60)

        color = (255, 200, 0, alpha)
        border_color = (255, 200, 0, 160)
        if self._body_count > 0:
            border_color = (255, 100, 0, 255)

        canvas.draw_rectangle(
            rect=(world.position[0], world.position[1], self._w, self._h),
            color=color,
            border_color=border_color,
            thickness=2.0,
            rotation=world.rotation,
            origin=(hw, hh),
        )

        # Label
        canvas.draw_text(
            text=f"Bodies: {self._body_count}",
            pos=(world.position[0] - 30, world.position[1] - 8),
            font_size=14,
            color=(255, 255, 255, 200),
        )


# ======================================================================
# HUD
# ======================================================================


class HUD(pu.NodeUnit):
    """Tampilan informasi di atas layar."""

    def __init__(self) -> None:
        super().__init__(name="HUD")
        self.layer = 100  # Render di atas physics
        self._debug_enabled = True
        self._gravity_on = True

    def on_ready(self) -> None:
        self._physics = self.one_or_none("Physics", scope="global")

    def draw(self, canvas: pu.Canvas) -> None:
        if self._physics is None:
            return

        physics: pu.Physics = self._physics

        y = 10
        canvas.draw_text(
            text="Plyunit Physics Demo",
            pos=(10, y),
            font_size=20,
            color=(255, 255, 255, 255),
        )
        y += 28

        grav = physics.gravity
        canvas.draw_text(
            text=f"Bodies: {physics.body_count} | Statics: {physics.static_count} "
            f"| Areas: {physics.area_count}",
            pos=(10, y),
            font_size=14,
            color=(200, 200, 200, 255),
        )
        y += 20

        canvas.draw_text(
            text=f"Gravity: ({grav[0]:.0f}, {grav[1]:.0f})",
            pos=(10, y),
            font_size=14,
            color=(200, 200, 200, 255),
        )
        y += 24

        canvas.draw_text(
            text="LMB: Box | RMB: Circle | Space: Gravity | D: Debug | R: Reset",
            pos=(10, y),
            font_size=12,
            color=(150, 150, 150, 255),
        )


# ======================================================================
# Scene
# ======================================================================


class PhysicsScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("PhysicsScene")
        self._physics: pu.Physics | None = None
        self._debug_draw: pu.PhysicsDebugDraw | None = None
        self._debug_node: pu.NodeUnit | None = None
        self._spawn_counter = 0
        self._gravity_on = True

    def on_load(self) -> None:
        # Buat physics service

        self._gravity_on = True

        # Floor — static body via QuadTree
        floor = pu.StaticBody(
            position=(400, 560),
            shapes=[pu.BoxShape(width=760, height=32, friction=0.8, elasticity=0.2)],
        )
        floor.filter.set_layer_bit(LAYER_WORLD, True)

        self._physics = self.one("@Physics")
        self._physics.add_static(floor)

        # Left wall
        left_wall = pu.StaticBody(
            position=(20, 300),
            shapes=[pu.BoxShape(width=20, height=520, friction=0.5)],
        )
        left_wall.filter.set_layer_bit(LAYER_WORLD, True)
        self._physics.add_static(left_wall)

        # Right wall
        right_wall = pu.StaticBody(
            position=(780, 300),
            shapes=[pu.BoxShape(width=20, height=520, friction=0.5)],
        )
        right_wall.filter.set_layer_bit(LAYER_WORLD, True)
        self._physics.add_static(right_wall)

        # Angled ramp (static segment)
        ramp = pu.StaticBody(
            position=(0, 0),
            shapes=[
                pu.SegmentShape(
                    a=(200, 400), b=(400, 450), radius=3, friction=0.4, elasticity=0.3
                )
            ],
        )
        ramp.filter.set_layer_bit(LAYER_WORLD, True)
        self._physics.add_static(ramp)

        # Small shelf
        shelf = pu.StaticBody(
            position=(600, 380),
            shapes=[pu.BoxShape(width=100, height=12, friction=0.6)],
        )
        shelf.filter.set_layer_bit(LAYER_WORLD, True)
        self._physics.add_static(shelf)

        # Moving platform
        platform = pu.NodeUnit(name="MovingPlatform")
        platform.add_component(MovingPlatform(400, 300))
        self.root.attach(platform)

        # Trigger zone
        trigger = pu.NodeUnit(name="TriggerZone")
        trigger.add_component(TriggerZone(400, 500, 100, 60))
        self.root.attach(trigger)

        # Spawn beberapa initial objects
        for i in range(5):
            box = pu.NodeUnit(name="FallingBox")
            box.add_component(
                FallingBox(
                    150 + i * 60,
                    100 + random.randint(-50, 50),
                    w=random.randint(20, 40),
                    h=random.randint(20, 40),
                    color_idx=i,
                )
            )
            self.root.attach(box)

        for i in range(3):
            circle = pu.NodeUnit(name="FallingCircle")
            circle.add_component(
                FallingCircle(
                    300 + i * 80,
                    50 + random.randint(-30, 30),
                    radius=random.randint(10, 24),
                )
            )
            self.root.attach(circle)

        # HUD
        self.root.attach(HUD())

        # Debug draw node + component
        self._debug_node = pu.NodeUnit(name="DebugDrawNode")
        self._debug_draw = pu.PhysicsDebugDraw(
            draw_bodies=True,
            draw_statics=True,
            draw_areas=True,
            draw_contacts=True,
        )
        self._debug_node.add_component(self._debug_draw)
        self.root.attach(self._debug_node)

    def on_unload(self) -> None:
        if self._physics:
            self._physics.clear_statics()

    def update(self, dt: float) -> None:
        # Physics di-step otomatis oleh Physics.on_attach (init).
        # Input handling
        self._handle_input(dt)

    def _handle_input(self, dt: float) -> None:
        _ = dt
        kb = self.one("@Input", scope="global")
        mouse = self.one("@Mouse", scope="global")

        # Spawn box (edges auto-gated to first fixed substep)
        if mouse.is_pressed("left"):
            mx, my = mouse.x, mouse.y
            if my > 80:  # Tidak spawn di area HUD
                box = pu.NodeUnit(name="FallingBox")
                box_renderer = box.add_component(
                    FallingBox(
                        mx,
                        my,
                        w=random.randint(18, 38),
                        h=random.randint(18, 38),
                        color_idx=self._spawn_counter,
                    )
                )
                # Random spin
                self.root.attach(box)
                box_renderer.angular_velocity = random.uniform(-200, 200)
                self._spawn_counter += 1

        # Spawn circle
        if mouse.is_pressed("right"):
            mx, my = mouse.x, mouse.y
            if my > 80:
                circle = pu.NodeUnit(name="FallingCircle")
                circle_renderer = circle.add_component(
                    FallingCircle(
                        mx,
                        my,
                        radius=random.randint(8, 22),
                    )
                )
                self.root.attach(circle)
                circle_renderer.angular_velocity = random.uniform(-300, 300)

        # Toggle gravity
        if kb.is_pressed("toggle_gravity") and self._physics:
            if self._gravity_on:
                self._physics.set_gravity(0, 0)
            else:
                self._physics.set_gravity(0, 900)
            self._gravity_on = not self._gravity_on

        # Toggle debug draw
        if kb.is_pressed("toggle_debug"):  # noqa: SIM102
            if self._debug_node and self._debug_draw:
                if self._debug_draw.enabled:
                    self._debug_draw.enabled = False
                else:
                    self._debug_draw.enabled = True

        # Reset
        if kb.is_pressed("reset"):
            app = self.one("App", scope="global")
            if isinstance(app, pu.App):
                app.scene_manager.change(PhysicsScene())


# ======================================================================
# App
# ======================================================================


class PhysicsApp(pu.App):
    def on_load(self) -> None:
        self.input = pu.Input()
        self.mouse = pu.Mouse()
        self.input.map("toggle_gravity", pr.KeyboardKey.KEY_SPACE)
        self.input.map("toggle_debug", pr.KeyboardKey.KEY_D)
        self.input.map("reset", pr.KeyboardKey.KEY_R)
        self.scene_manager.push(PhysicsScene())

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background(self.config.background_color)
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def main():
    app = pu.init(
        PhysicsApp(),
        pu.AppConfig(
            title="Plyunit Physics Demo",
            window_width=800,
            window_height=600,
            background_color=pr.Color(25, 25, 35, 255),
            physics=pu.PhysicsConfig(
                enabled=True,
                gravity=(0, 900),
                world_bounds=(-500, -500, 1300, 1100),
            ),
        ),
    )
    app.run()


if __name__ == "__main__":
    main()

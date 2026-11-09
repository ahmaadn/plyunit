"""Apply a time-driven wave and color-pulse shader to a sprite.

The selected ``Shaders`` service owns shader handles and caches uniform
locations. Generated images and textures use the raylib integration's handles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyray as pr

import plyunit as pu
from plyunit._enums import ShaderUniform
from plyunit.backends.ports.renderer import ICanvas2D

if TYPE_CHECKING:
    from plyunit.backends.integrations.raylib.handler import Shader, Texture2D
    from plyunit.backends.integrations.raylib.shader import Shaders

# GLSL 330 fragment shader: sine-wave distortion and a pulsing color tint.
FS_CODE = """#version 330
in vec2 fragTexCoord;
in vec4 fragColor;

uniform sampler2D texture0;
uniform vec4 colDiffuse;
uniform float time;

out vec4 finalColor;

void main()
{
    vec2 uv = fragTexCoord;

    // Animate the sine-wave distortion over time.
    uv.x += sin(uv.y * 50.0 + time * 5.0) * 0.02;
    uv.y += cos(uv.x * 50.0 + time * 3.0) * 0.02;

    vec4 texelColor = texture(texture0, uv);

    // Blend between red and blue tints.
    float pulse = (sin(time * 2.0) + 1.0) / 2.0;
    vec3 tint = mix(vec3(1.0, 0.2, 0.2), vec3(0.2, 0.5, 1.0), pulse);

    finalColor = vec4(texelColor.rgb * tint, texelColor.a) * colDiffuse * fragColor;
}
"""

VS_CODE = """#version 330
in vec3 vertexPosition;
in vec2 vertexTexCoord;
in vec4 vertexColor;
out vec2 fragTexCoord;
out vec4 fragColor;
uniform mat4 mvp;
void main()
{
    fragTexCoord = vertexTexCoord;
    fragColor = vertexColor;
    gl_Position = mvp*vec4(vertexPosition, 1.0);
}
"""


class ShaderSprite(pu.NodeUnit):
    """Draw a sprite with an optional shader owned by the shader service."""

    def __init__(self, x: float, y: float, use_shader: bool = True) -> None:
        super().__init__(name="ShaderSprite")
        self.start_x = x
        self.start_y = y
        self.use_shader = use_shader
        self.time = 0.0

        # GPU resources are created in on_ready, after the window exists.
        self.shaders: Shaders | None = None
        self.tex: Texture2D | None = None
        self.shader_handle: Shader | None = None
        self.layer = pu.Layer.ENTITIES

    def on_ready(self) -> None:
        from plyunit.backends.integrations.raylib.handler import Image, Texture2D

        shaders: Shaders = self.one("@Shaders")
        self.shaders = shaders

        image = Image(pr.gen_image_checked(200, 200, 25, 25, pr.WHITE, pr.DARKGRAY))
        try:
            self.tex = Texture2D.from_raw(pr.load_texture_from_image(image.raw_image))
        finally:
            pr.unload_image(image.raw_image)

        if self.use_shader:
            self.shader_handle = shaders.load_from_memory(VS_CODE, FS_CODE)
            # Render state carries the handle, never its backend shader struct.
            self.set_shader(self.shader_handle)

        self.transform.set_position(self.start_x, self.start_y)

    def update(self, dt: float) -> None:
        self.time += dt

        # Uniform locations are cached by name on the shader handle.
        if self.shaders is not None and self.shader_handle is not None:
            self.shaders.set_value(
                self.shader_handle, "time", self.time, ShaderUniform.FLOAT
            )

    def draw(self, canvas: ICanvas2D) -> None:
        if not self.tex:
            return

        wt = self.world_transform_lerp()
        x, y = wt.position

        canvas.draw_texture(
            texture=self.tex, pos=(x - 100, y - 100), tint=(255, 255, 255, 255)
        )

    def on_exit_tree(self) -> None:
        """Release node-owned GPU resources when the scene removes this node."""
        if self.tex is not None:
            pr.unload_texture(self.tex.raw_texture)
            self.tex = None
        if self.shaders is not None and self.shader_handle is not None:
            self.set_shader(None)
            self.shaders.unload(self.shader_handle)
            self.shader_handle = None
        super().on_exit_tree()


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main", tags={"main"})

    def on_load(self) -> None:
        # Title
        title = pu.NodeUnit("Title")
        title.layer = pu.Layer.UI
        title.draw = lambda canvas: canvas.draw_text(
            text="Custom Shader (Wave & Color Pulse)",
            pos=(150, 30),
            font_size=20,
            color=(255, 255, 255, 255),
        )
        self.root.attach(title)

        # Left: unshaded sprite
        normal_sprite = ShaderSprite(180, 250, use_shader=False)
        self.root.attach(normal_sprite)

        lbl_normal = pu.NodeUnit("LblNormal")
        lbl_normal.layer = pu.Layer.UI
        lbl_normal.draw = lambda canvas: canvas.draw_text(
            text="NORMAL",
            pos=(140, 380),
            font_size=20,
            color=(200, 200, 200, 255),
        )
        self.root.attach(lbl_normal)

        # Right: shader applied
        shader_sprite = ShaderSprite(460, 250, use_shader=True)
        self.root.attach(shader_sprite)

        lbl_shader = pu.NodeUnit("LblShader")
        lbl_shader.layer = pu.Layer.UI
        lbl_shader.draw = lambda canvas: canvas.draw_text(
            text="SHADER APPLIED",
            pos=(380, 380),
            font_size=20,
            color=(253, 249, 0, 255),
        )
        self.root.attach(lbl_shader)


class ShaderApp(pu.App):
    def on_load(self) -> None:
        self.shaders = pu.Shaders()
        self.scene_manager.push(MainScene())

    def fixed_update(self, dt: float, step: int) -> None:
        _ = step
        self.scene_manager.update(dt)
        self.scene_manager.apply_pending()

    def update(self, dt: float) -> None:
        _ = dt
        self.renderer.reset_frame()
        self.window.begin_drawing()
        self.window.clear_background((20, 20, 30, 255))
        self.scene_manager.render(self.renderer)
        self.renderer.flush_all()
        self.window.end_drawing()


def main():
    app = pu.init(
        ShaderApp(),
        pu.AppConfig(
            title="Shader Example",
            window_width=640,
            window_height=480,
        ),
    )
    app.run()


if __name__ == "__main__":
    main()

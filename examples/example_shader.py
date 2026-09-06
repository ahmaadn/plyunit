"""Example: Custom Shader

Demonstrasi penggunaan custom GLSL shader pada plyunit melalui layanan
``pu.Shaders`` yang membungkus backend loader raylib
(``plyunit.backends.integrations.raylib.assets.shader``).
Kita memuat fragment shader sederhana yang memberikan efek gelombang (wavy)
dan color pulse pada sebuah sprite.

Kontrol:
- Tidak ada (efek berjalan otomatis berdasarkan waktu)
"""

import pyray as pr

import plyunit as pu

# Fragment Shader sederhana (GLSL 330)
# Efek: Sinewave distortion + Grayscale mix
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

    // Gelombang sinewave berdasarkan waktu
    uv.x += sin(uv.y * 50.0 + time * 5.0) * 0.02;
    uv.y += cos(uv.x * 50.0 + time * 3.0) * 0.02;

    vec4 texelColor = texture(texture0, uv);

    // Campur dengan warna merah & biru yang berkedip
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
    """Sprite yang di-render dengan custom shader dari layanan ``Shaders``."""

    def __init__(self, x: float, y: float, use_shader: bool = True) -> None:
        super().__init__(name="ShaderSprite")
        self.start_x = x
        self.start_y = y
        self.use_shader = use_shader
        self.time = 0.0

        # Layanan shader, texture, dan handle akan diisi di on_ready
        # (setelah Raylib window aktif). Catatan: atribut ``shader`` milik
        # NodeUnit adalah slot render-state (shader mentah), jadi handle
        # disimpan terpisah di ``shader_handle``.
        self.shaders: pu.Shaders | None = None
        self.tex = None
        self.shader_handle: pu.ShaderHandle | None = None
        self.layer = pu.Layer.ENTITIES

    def on_ready(self) -> None:
        # Ambil layanan shader global (dibuat di ShaderApp.on_load)
        shaders: pu.Shaders = self.one("@Shaders")
        self.shaders = shaders

        # Generate gambar checkerboard
        img = pr.gen_image_checked(200, 200, 25, 25, pr.WHITE, pr.DARKGRAY)
        self.tex = pr.load_texture_from_image(img)
        pr.unload_image(img)

        if self.use_shader:
            # Muat shader via layanan Shaders (backend: raylib shader loader)
            handle = shaders.load_from_memory(VS_CODE, FS_CODE)
            self.shader_handle = handle
            # Aktifkan shader untuk node ini; Renderer otomatis
            # mengaktifkan shader-nya saat pass render!
            self.set_shader(handle.raw)

        # Set posisi awal
        self.transform.set_position(self.start_x, self.start_y)

    def update(self, dt: float) -> None:
        self.time += dt

        # Set uniform 'time' berdasarkan nama (lokasi di-cache oleh layanan)
        if self.shaders is not None and self.shader_handle is not None:
            self.shaders.set_value(
                self.shader_handle, "time", self.time, pu.ShaderUniform.FLOAT
            )

    def draw(self, canvas: pu.interfaces.ICanvas2D) -> None:
        if not self.tex:
            return

        wt = self.world_transform_lerp()
        x, y = wt.position

        canvas.draw_texture(
            texture=self.tex, pos=(x - 100, y - 100), tint=(255, 255, 255, 255)
        )

    def destroy(self) -> None:
        if self.tex:
            pr.unload_texture(self.tex)
        if self.shaders is not None and self.shader_handle is not None:
            self.shaders.unload(self.shader_handle)
            self.shader_handle = None
        super().destroy()


class MainScene(pu.SceneUnit):
    def __init__(self) -> None:
        super().__init__("Main", tags={"main"})

    def on_load(self) -> None:
        # Judul
        title = pu.NodeUnit("Title")
        title.layer = pu.Layer.UI
        title.draw = lambda canvas: canvas.draw_text(
            text="Custom Shader (Wave & Color Pulse)",
            pos=(150, 30),
            font_size=20,
            # pyrefly: ignore [bad-argument-type]
            color=pr.WHITE,
        )
        self.root.attach(title)

        # Sprite 1: Tanpa Shader (Kiri)
        normal_sprite = ShaderSprite(180, 250, use_shader=False)
        self.root.attach(normal_sprite)

        lbl_normal = pu.NodeUnit("LblNormal")
        lbl_normal.layer = pu.Layer.UI
        lbl_normal.draw = lambda canvas: canvas.draw_text(
            text="NORMAL",
            pos=(140, 380),
            font_size=20,
            # pyrefly: ignore [bad-argument-type]
            color=pr.LIGHTGRAY,
        )
        self.root.attach(lbl_normal)

        # Sprite 2: Dengan Shader (Kanan)
        shader_sprite = ShaderSprite(460, 250, use_shader=True)
        self.root.attach(shader_sprite)

        lbl_shader = pu.NodeUnit("LblShader")
        lbl_shader.layer = pu.Layer.UI
        lbl_shader.draw = lambda canvas: canvas.draw_text(
            text="SHADER APPLIED",
            pos=(380, 380),
            font_size=20,
            # pyrefly: ignore [bad-argument-type]
            color=pr.YELLOW,
        )
        self.root.attach(lbl_shader)


class ShaderApp(pu.App):
    def on_load(self) -> None:
        # Layanan shader global; delegasi load/uniform/unload ke backend
        # raylib (plyunit.backends.integrations.raylib.assets.shader)
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
        self.window.clear_background(self.config.background_color)
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
            # pyrefly: ignore [bad-argument-type]
            background_color=pr.Color(20, 20, 30, 255),
        ),
    )
    app.run()


if __name__ == "__main__":
    main()

"""Service layar raylib (pyray) dalam satu file. Butuh raylib >= 5.0.

Isi (berurutan):
    1. Tata letak murni  : DisplayMode, ScaleMode, Size, Viewport, compute_viewport
    2. Waktu frame       : clamp_delta, FixedTimestep
    3. DisplayService    : window/borderless/fullscreen, kanvas virtual, mouse
    4. Hook loop modal   : prototipe Win32 agar game tetap jalan saat window digeser
    5. Demo              : jalankan `python display_all_in_one.py`

Kontrol demo:
    Panah/WASD : gerak     F11 : borderless     F10 : fullscreen
    F1..F4     : LETTERBOX / INTEGER / STRETCH / EXPAND
    F5..F7     : ukuran window 1280x720 / 1600x900 / 1920x1080
    --no-modal-hook : matikan hook loop modal (untuk perbandingan, Windows)
"""

from __future__ import annotations

import logging
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

import pyray as rl

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Tata letak murni (tanpa raylib; mudah diuji)
#    window   = ukuran jendela sebenarnya (piksel fisik)
#    virtual  = ukuran "kanvas game" tempat semua gambar dibuat
#    viewport = persegi di dalam window tempat kanvas virtual ditampilkan
# =============================================================================


class InvalidSizeError(ValueError):
    """Ukuran layar harus bernilai positif."""


class DisplayMode(Enum):
    WINDOWED = auto()
    BORDERLESS = auto()  # jendela tanpa bingkai seukuran monitor (aman untuk alt-tab)
    FULLSCREEN = auto()  # fullscreen eksklusif


class ScaleMode(Enum):
    LETTERBOX = auto()  # skala pecahan, rasio dijaga, ada bar hitam
    INTEGER = auto()  # skala bilangan bulat (pixel-perfect)
    STRETCH = auto()  # penuhi window, rasio bisa terdistorsi
    EXPAND = auto()  # tanpa skala: area pandang bertambah mengikuti window


@dataclass(frozen=True)
class Size:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise InvalidSizeError(f"Ukuran tidak valid: {self.width}x{self.height}")


@dataclass(frozen=True)
class Viewport:
    x: float
    y: float
    width: float
    height: float
    scale_x: float
    scale_y: float


@dataclass(frozen=True)
class DisplaySettings:
    virtual_size: Size = Size(1280, 720)
    window_size: Size = Size(1280, 720)
    min_window_size: Size = Size(640, 360)
    display_mode: DisplayMode = DisplayMode.WINDOWED
    scale_mode: ScaleMode = ScaleMode.LETTERBOX
    target_fps: int = 60  # dipakai hanya bila vsync mati
    vsync: bool = (
        True  # sinkron dengan refresh monitor: frame pacing rata, tanpa tearing
    )


def resolve_virtual_size(window: Size, base: Size, mode: ScaleMode) -> Size:
    """Ukuran kanvas virtual. Pada EXPAND, kanvas selalu sama dengan window."""
    return window if mode is ScaleMode.EXPAND else base


def _uniform_scale(window: Size, virtual: Size, mode: ScaleMode) -> float:
    if mode is ScaleMode.EXPAND:
        return 1.0
    fit = min(window.width / virtual.width, window.height / virtual.height)
    if mode is ScaleMode.INTEGER and fit >= 1.0:
        return float(math.floor(fit))
    return fit


def compute_viewport(window: Size, virtual: Size, mode: ScaleMode) -> Viewport:
    """Hitung posisi & skala kanvas virtual di dalam window."""
    if mode is ScaleMode.STRETCH:
        return Viewport(
            0.0,
            0.0,
            float(window.width),
            float(window.height),
            window.width / virtual.width,
            window.height / virtual.height,
        )
    scale = _uniform_scale(window, virtual, mode)
    width, height = virtual.width * scale, virtual.height * scale
    return Viewport(
        float(math.floor((window.width - width) / 2)),
        float(math.floor((window.height - height) / 2)),
        width,
        height,
        scale,
        scale,
    )


def window_to_virtual(
    point: tuple[float, float], viewport: Viewport
) -> tuple[float, float]:
    """Ubah koordinat piksel window menjadi koordinat kanvas virtual."""
    return (
        (point[0] - viewport.x) / viewport.scale_x,
        (point[1] - viewport.y) / viewport.scale_y,
    )


# =============================================================================
# 2. Waktu frame: cegah "teleport" setelah window digeser/di-resize
# =============================================================================

MAX_FRAME_SECONDS = 1.0 / 20.0  # frame lebih lama dari 50 ms dianggap "stall"
DEFAULT_STEP_SECONDS = 1.0 / 60.0
DEFAULT_MAX_STEPS = 5


def clamp_delta(raw_delta: float, limit: float = MAX_FRAME_SECONDS) -> float:
    """Batasi delta time agar stall (drag window, breakpoint) tidak jadi lompatan."""
    return min(max(raw_delta, 0.0), limit)


class FixedTimestep:
    """Akumulator timestep tetap: simulasi selalu maju dengan langkah yang sama.

    Contoh:
        stepper = FixedTimestep()
        for _ in range(stepper.advance(rl.get_frame_time())):
            update(stepper.step)
    """

    def __init__(
        self,
        step: float = DEFAULT_STEP_SECONDS,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> None:
        self.step = step
        self._max_steps = max_steps
        self._accumulator = 0.0

    def advance(self, raw_delta: float) -> int:
        """Tambahkan waktu dan kembalikan jumlah langkah simulasi yang harus dijalankan."""
        self._accumulator += max(raw_delta, 0.0)
        steps = 0
        while self._accumulator >= self.step and steps < self._max_steps:
            self._accumulator -= self.step
            steps += 1
        if self._accumulator >= self.step:  # backlog terlalu besar: buang
            self._accumulator = 0.0
        return steps


# =============================================================================
# 3. DisplayService
#    Alur per frame:
#        display.update()        # sinkronkan ukuran window
#        display.begin_frame()   # mulai menggambar ke kanvas virtual
#        ... gambar game ...
#        display.end_frame()     # tampilkan kanvas ke window (skala/letterbox)
# =============================================================================


class DisplayNotOpenError(RuntimeError):
    """Dipanggil sebelum open()."""


class DisplayService:
    """Mengelola window, fullscreen, kanvas virtual, dan pemetaan mouse."""

    def __init__(self, settings: DisplaySettings) -> None:
        self._settings = settings
        self._mode = DisplayMode.WINDOWED
        self._scale_mode = settings.scale_mode
        self._windowed_size = settings.window_size
        self._window_size = settings.window_size
        self._virtual = resolve_virtual_size(
            settings.window_size, settings.virtual_size, settings.scale_mode
        )
        self._viewport = compute_viewport(
            self._window_size, self._virtual, self._scale_mode
        )
        self._target: rl.RenderTexture | None = None

    # ---- properti baca-saja -------------------------------------------------
    @property
    def virtual_size(self) -> Size:
        return self._virtual

    @property
    def window_size(self) -> Size:
        return self._window_size

    @property
    def display_mode(self) -> DisplayMode:
        return self._mode

    @property
    def scale_mode(self) -> ScaleMode:
        return self._scale_mode

    @property
    def viewport(self) -> Viewport:
        return self._viewport

    # ---- siklus hidup -------------------------------------------------------
    def open(self, title: str) -> None:
        """Buat window sesuai settings awal."""
        s = self._settings
        flags = rl.FLAG_WINDOW_RESIZABLE
        if s.vsync:
            flags |= rl.FLAG_VSYNC_HINT
        rl.set_config_flags(flags)
        rl.init_window(s.window_size.width, s.window_size.height, title)
        rl.set_window_min_size(s.min_window_size.width, s.min_window_size.height)
        if (
            not s.vsync
        ):  # vsync + target fps yang berbeda dari refresh rate memicu judder
            rl.set_target_fps(s.target_fps)
        self._refresh_layout(force=True)
        self.set_display_mode(s.display_mode)

    def close(self) -> None:
        if self._target is not None:
            rl.unload_render_texture(self._target)
            self._target = None
        rl.close_window()

    # ---- perintah publik ----------------------------------------------------
    def update(self) -> None:
        """Panggil di awal tiap frame: mendeteksi perubahan ukuran window."""
        self._refresh_layout()

    def set_display_mode(self, mode: DisplayMode) -> None:
        self._refresh_layout()
        if mode is self._mode:
            return
        previous, self._mode = self._mode, mode
        self._leave_mode(previous)
        self._enter_mode(mode)
        self._refresh_layout()

    def toggle_borderless(self) -> None:
        target = (
            DisplayMode.WINDOWED
            if self._mode is DisplayMode.BORDERLESS
            else DisplayMode.BORDERLESS
        )
        self.set_display_mode(target)

    def toggle_fullscreen(self) -> None:
        target = (
            DisplayMode.WINDOWED
            if self._mode is DisplayMode.FULLSCREEN
            else DisplayMode.FULLSCREEN
        )
        self.set_display_mode(target)

    def set_window_size(self, size: Size) -> None:
        """Ubah ukuran window. Di mode non-windowed, disimpan untuk nanti."""
        self._windowed_size = size
        if self._mode is DisplayMode.WINDOWED:
            rl.set_window_size(size.width, size.height)
            self._center_window()
        self._refresh_layout()

    def set_scale_mode(self, mode: ScaleMode) -> None:
        self._scale_mode = mode
        self._refresh_layout(force=True)

    # ---- menggambar ---------------------------------------------------------
    def begin_frame(self) -> None:
        rl.begin_texture_mode(self._require_target())

    def end_frame(self) -> None:
        """Akhiri kanvas virtual lalu gambar ke window sesuai viewport."""
        target = self._require_target()
        rl.end_texture_mode()
        vp = self._viewport
        source = rl.Rectangle(
            0, 0, self._virtual.width, -self._virtual.height
        )  # RT terbalik
        dest = rl.Rectangle(vp.x, vp.y, vp.width, vp.height)
        rl.begin_drawing()
        rl.clear_background(rl.BLACK)
        rl.draw_texture_pro(
            target.texture, source, dest, rl.Vector2(0, 0), 0.0, rl.WHITE
        )
        rl.end_drawing()

    # ---- internal -----------------------------------------------------------
    def _require_target(self) -> rl.RenderTexture:
        if self._target is None:
            raise DisplayNotOpenError("Panggil DisplayService.open() terlebih dahulu.")
        return self._target

    def _leave_mode(self, previous: DisplayMode) -> None:
        if previous is DisplayMode.FULLSCREEN:
            rl.toggle_fullscreen()
        elif previous is DisplayMode.BORDERLESS:
            rl.toggle_borderless_windowed()

    def _enter_mode(self, mode: DisplayMode) -> None:
        if mode is DisplayMode.WINDOWED:
            rl.set_window_size(self._windowed_size.width, self._windowed_size.height)
            self._center_window()
        elif mode is DisplayMode.BORDERLESS:
            rl.toggle_borderless_windowed()
        else:
            monitor = rl.get_current_monitor()
            rl.set_window_size(
                rl.get_monitor_width(monitor), rl.get_monitor_height(monitor)
            )
            rl.toggle_fullscreen()

    def _center_window(self) -> None:
        monitor = rl.get_current_monitor()
        origin = rl.get_monitor_position(monitor)
        x = origin.x + (rl.get_monitor_width(monitor) - rl.get_screen_width()) // 2
        y = origin.y + (rl.get_monitor_height(monitor) - rl.get_screen_height()) // 2
        rl.set_window_position(int(x), int(max(y, 0)))

    def _refresh_layout(self, force: bool = False) -> None:
        width, height = rl.get_screen_width(), rl.get_screen_height()
        if width <= 0 or height <= 0:  # window sedang minimize
            return
        size = Size(width, height)
        if not force and size == self._window_size:
            return
        self._window_size = size
        if self._mode is DisplayMode.WINDOWED:
            self._windowed_size = size
        self._rebuild_layout(size)

    def _rebuild_layout(self, window: Size) -> None:
        virtual = resolve_virtual_size(
            window, self._settings.virtual_size, self._scale_mode
        )
        self._viewport = compute_viewport(window, virtual, self._scale_mode)
        if virtual != self._virtual or self._target is None:
            self._virtual = virtual
            self._rebuild_target()
        self._apply_texture_filter()
        self._apply_mouse_mapping()

    def _rebuild_target(self) -> None:
        if self._target is not None:
            rl.unload_render_texture(self._target)
        self._target = rl.load_render_texture(self._virtual.width, self._virtual.height)

    def _apply_texture_filter(self) -> None:
        crisp = self._scale_mode in (ScaleMode.INTEGER, ScaleMode.EXPAND)
        mode = rl.TEXTURE_FILTER_POINT if crisp else rl.TEXTURE_FILTER_BILINEAR
        rl.set_texture_filter(self._require_target().texture, mode)

    def _apply_mouse_mapping(self) -> None:
        """Agar get_mouse_position() mengembalikan koordinat kanvas virtual."""
        vp = self._viewport
        rl.set_mouse_offset(-int(vp.x), -int(vp.y))
        rl.set_mouse_scale(1.0 / vp.scale_x, 1.0 / vp.scale_y)


# =============================================================================
# 4. Hook loop modal Win32 (PROTOTIPE)
#    Saat title bar ditahan, Windows memblokir thread utama di loop modal,
#    tetapi tetap mengirim WM_TIMER ke window procedure. WM_ENTERSIZEMOVE
#    memulai timer, WM_TIMER menjalankan satu frame, WM_EXITSIZEMOVE
#    menghentikannya. Logika kontroler diuji otomatis; bagian Win32 belum
#    pernah dijalankan di Windows nyata.
# =============================================================================

WM_TIMER = 0x0113
WM_ENTERSIZEMOVE = 0x0231
WM_EXITSIZEMOVE = 0x0232
TIMER_ID = 0x7A11
TICK_INTERVAL_MS = 16  # resolusi timer Windows ~15.6 ms


class UnsupportedPlatformError(RuntimeError):
    """Hook ini hanya tersedia di Windows."""


class ModalAction(Enum):
    NONE = auto()
    START_TIMER = auto()
    STOP_TIMER = auto()
    RUN_FRAME = auto()


class ModalLoopController:
    """Mesin status murni: pesan Windows -> aksi (mudah diuji tanpa Windows)."""

    def __init__(self) -> None:
        self._in_modal = False
        self._in_frame = False

    def on_message(self, message: int, wparam: int = 0) -> ModalAction:
        """Tentukan aksi untuk sebuah pesan. RUN_FRAME harus diakhiri frame_finished()."""
        if message == WM_ENTERSIZEMOVE:
            self._in_modal = True
            return ModalAction.START_TIMER
        if message == WM_EXITSIZEMOVE:
            self._in_modal = False
            return ModalAction.STOP_TIMER
        if self._should_run_frame(message, wparam):
            self._in_frame = True
            return ModalAction.RUN_FRAME
        return ModalAction.NONE

    def frame_finished(self) -> None:
        self._in_frame = False

    def _should_run_frame(self, message: int, wparam: int) -> bool:
        return (
            message == WM_TIMER
            and wparam == TIMER_ID
            and self._in_modal
            and not self._in_frame  # cegah rekursi: end_drawing() mem-polling event
        )


class _Win32Api:
    """Pembungkus ctypes tipis untuk fungsi Win32 yang dipakai (hanya Windows)."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)
        self.proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            ctypes.c_size_t,
            ctypes.c_size_t,
        )
        self.set_timer = user32.SetTimer
        self.set_timer.argtypes = [
            wintypes.HWND,
            ctypes.c_size_t,
            wintypes.UINT,
            ctypes.c_void_p,
        ]
        self.set_timer.restype = ctypes.c_size_t
        self.kill_timer = user32.KillTimer
        self.kill_timer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        self.set_window_subclass = comctl32.SetWindowSubclass
        self.set_window_subclass.argtypes = [
            wintypes.HWND,
            self.proc_type,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]
        self.remove_window_subclass = comctl32.RemoveWindowSubclass
        self.remove_window_subclass.argtypes = [
            wintypes.HWND,
            self.proc_type,
            ctypes.c_size_t,
        ]
        self.def_subclass_proc = comctl32.DefSubclassProc
        self.def_subclass_proc.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.def_subclass_proc.restype = ctypes.c_ssize_t


class Win32ModalHook:
    """Memasang subclass pada window agar frame tetap berjalan selama loop modal."""

    def __init__(
        self,
        frame: Callable[[], None],
        controller: ModalLoopController | None = None,
    ) -> None:
        self._frame = frame
        self._controller = controller or ModalLoopController()
        self._hwnd = 0
        self._callback: object | None = None  # simpan referensi agar tidak di-GC
        self._api: _Win32Api | None = None

    def install(self, hwnd: int) -> None:
        if sys.platform != "win32":
            raise UnsupportedPlatformError("Win32ModalHook hanya untuk Windows.")
        self._api = _Win32Api()
        self._hwnd = hwnd
        self._callback = self._api.proc_type(self._subclass_proc)
        if not self._api.set_window_subclass(hwnd, self._callback, TIMER_ID, 0):
            raise OSError("SetWindowSubclass gagal.")

    def uninstall(self) -> None:
        if self._api is None or not self._hwnd:
            return
        self._api.kill_timer(self._hwnd, TIMER_ID)
        self._api.remove_window_subclass(self._hwnd, self._callback, TIMER_ID)
        self._hwnd = 0
        self._callback = None

    def _subclass_proc(
        self, hwnd: int, message: int, wparam: int, lparam: int, _uid: int, _ref: int
    ) -> int:
        self._perform(self._controller.on_message(message, wparam), hwnd)
        assert self._api is not None
        return self._api.def_subclass_proc(hwnd, message, wparam, lparam)

    def _perform(self, action: ModalAction, hwnd: int) -> None:
        assert self._api is not None
        if action is ModalAction.START_TIMER:
            self._api.set_timer(hwnd, TIMER_ID, TICK_INTERVAL_MS, None)
        elif action is ModalAction.STOP_TIMER:
            self._api.kill_timer(hwnd, TIMER_ID)
        elif action is ModalAction.RUN_FRAME:
            self._run_frame_safely()

    def _run_frame_safely(self) -> None:
        try:
            self._frame()
        except (
            Exception
        ):  # batas callback ctypes: exception tidak boleh lolos ke Windows
            logger.exception("Frame di dalam loop modal gagal.")
        finally:
            self._controller.frame_finished()


# =============================================================================
# 5. Demo: DisplayService + kamera 2D + clamp delta time
# =============================================================================

NO_MODAL_HOOK_FLAG = "--no-modal-hook"
WORLD_SIZE = 2000
GRID_STEP = 100
PLAYER_SIZE = 40
PLAYER_SPEED = 320.0

SCALE_KEYS: dict[int, ScaleMode] = {
    rl.KEY_F1: ScaleMode.LETTERBOX,
    rl.KEY_F2: ScaleMode.INTEGER,
    rl.KEY_F3: ScaleMode.STRETCH,
    rl.KEY_F4: ScaleMode.EXPAND,
}
SIZE_KEYS: dict[int, Size] = {
    rl.KEY_F5: Size(1280, 720),
    rl.KEY_F6: Size(1600, 900),
    rl.KEY_F7: Size(1920, 1080),
}


@dataclass
class GameState:
    player: rl.Vector2


def handle_hotkeys(display: DisplayService) -> None:
    if rl.is_key_pressed(rl.KEY_F11):
        display.toggle_borderless()
    if rl.is_key_pressed(rl.KEY_F10):
        display.toggle_fullscreen()
    for key, mode in SCALE_KEYS.items():
        if rl.is_key_pressed(key):
            display.set_scale_mode(mode)
    for key, size in SIZE_KEYS.items():
        if rl.is_key_pressed(key):
            display.set_window_size(size)


def read_direction() -> rl.Vector2:
    dx = int(rl.is_key_down(rl.KEY_RIGHT) or rl.is_key_down(rl.KEY_D)) - int(
        rl.is_key_down(rl.KEY_LEFT) or rl.is_key_down(rl.KEY_A)
    )
    dy = int(rl.is_key_down(rl.KEY_DOWN) or rl.is_key_down(rl.KEY_S)) - int(
        rl.is_key_down(rl.KEY_UP) or rl.is_key_down(rl.KEY_W)
    )
    return rl.Vector2(dx, dy)


def move_player(
    position: rl.Vector2, direction: rl.Vector2, delta: float
) -> rl.Vector2:
    x = min(
        max(position.x + direction.x * PLAYER_SPEED * delta, 0),
        WORLD_SIZE - PLAYER_SIZE,
    )
    y = min(
        max(position.y + direction.y * PLAYER_SPEED * delta, 0),
        WORLD_SIZE - PLAYER_SIZE,
    )
    return rl.Vector2(x, y)


def snap(value: float) -> int:
    """Bulatkan ke piksel terdekat. Satu aturan untuk kamera DAN gambar agar tidak jitter."""
    return math.floor(value + 0.5)


def build_camera(virtual: Size, player: rl.Vector2) -> rl.Camera2D:
    """Offset kamera = tengah KANVAS VIRTUAL, bukan tengah window.

    Target dan offset dibulatkan ke integer: player tetap diam di tengah layar
    dan dunia bergeser dalam kelipatan piksel utuh (tidak ada 'lompat 1 piksel').
    """
    center = rl.Vector2(
        snap(player.x) + PLAYER_SIZE // 2, snap(player.y) + PLAYER_SIZE // 2
    )
    offset = rl.Vector2(virtual.width // 2, virtual.height // 2)
    return rl.Camera2D(offset, center, 0.0, 1.0)


def draw_world(player: rl.Vector2) -> None:
    for i in range(0, WORLD_SIZE + 1, GRID_STEP):
        rl.draw_line(i, 0, i, WORLD_SIZE, rl.LIGHTGRAY)
        rl.draw_line(0, i, WORLD_SIZE, i, rl.LIGHTGRAY)
    rl.draw_rectangle_lines(0, 0, WORLD_SIZE, WORLD_SIZE, rl.RED)
    rl.draw_rectangle(snap(player.x), snap(player.y), PLAYER_SIZE, PLAYER_SIZE, rl.BLUE)


def draw_hud(display: DisplayService, raw_delta: float) -> None:
    vp = display.viewport
    lines = [
        f"Window  : {display.window_size.width}x{display.window_size.height} ({display.display_mode.name})",
        f"Virtual : {display.virtual_size.width}x{display.virtual_size.height} ({display.scale_mode.name})",
        f"Scale   : {vp.scale_x:.2f} x {vp.scale_y:.2f}",
        f"Raw dt  : {raw_delta * 1000:.1f} ms (dipakai: {clamp_delta(raw_delta) * 1000:.1f} ms)",
    ]
    for index, line in enumerate(lines):
        rl.draw_text(line, 10, 10 + index * 22, 20, rl.DARKGRAY)


def run_frame(display: DisplayService, state: GameState) -> None:
    """Satu frame penuh. Dipanggil dari loop utama DAN dari hook loop modal."""
    raw_delta = rl.get_frame_time()
    display.update()
    handle_hotkeys(display)
    state.player = move_player(state.player, read_direction(), clamp_delta(raw_delta))

    display.begin_frame()
    rl.clear_background(rl.RAYWHITE)
    rl.begin_mode_2d(build_camera(display.virtual_size, state.player))
    draw_world(state.player)
    rl.end_mode_2d()
    draw_hud(display, raw_delta)
    display.end_frame()


def install_modal_hook(
    display: DisplayService, state: GameState
) -> Win32ModalHook | None:
    """Pasang hook hanya di Windows dan bila tidak dimatikan lewat --no-modal-hook."""
    if sys.platform != "win32" or NO_MODAL_HOOK_FLAG in sys.argv:
        return None
    hook = Win32ModalHook(lambda: run_frame(display, state))
    hook.install(int(rl.ffi.cast("uintptr_t", rl.get_window_handle())))
    return hook


def main() -> None:
    display = DisplayService(DisplaySettings())
    display.open("Display Service Demo")
    state = GameState(rl.Vector2(WORLD_SIZE / 2, WORLD_SIZE / 2))
    hook = install_modal_hook(display, state)
    try:
        while not rl.window_should_close():
            run_frame(display, state)
    finally:
        if hook is not None:
            hook.uninstall()
        display.close()


if __name__ == "__main__":
    main()

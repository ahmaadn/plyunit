"""Pemindaian project: satu kali walk, memangkas folder ter-exclude.

Implementasi lama memakai ``Path.rglob`` — lima kali untuk gambar
(:data:`~editor.constants.IMAGE_EXTENSIONS`) dan sekali lagi untuk map — lalu
menyaring hasilnya. Penyaringan setelah traversal tidak menolong: ``rglob``
sudah menelusuri ``.venv/Lib/site-packages`` sebelum satu pun hasil dibuang.

Modul ini menggantinya dengan satu traversal berbasis :func:`os.scandir` yang
**memangkas** folder ter-exclude sebelum masuk, dan menghasilkan kandidat gambar
serta kandidat map dalam sekali jalan.

Tidak ada satu pun panggilan raylib atau ImGui di sini, sehingga aman
dijalankan di thread pekerja (lihat :mod:`editor.core.scan_job`).
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import IntEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING, cast

import plyunit
from scripts import constants as const
from scripts.context import StatusType
from scripts.exclude import ExcludeRules
from scripts.services.assets import Assets

if TYPE_CHECKING:
    from main import EditorApp

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScanEntry:
    """Satu file yang ditemukan pemindaian.

    Attributes:
        path: Path absolut file.
        relative: Path relatif terhadap root pemindaian, separator posix.
        suffix: Ekstensi huruf kecil termasuk titik.
    """

    path: Path
    relative: str
    suffix: str
    data = None

    @property
    def is_image(self) -> bool:
        return self.suffix in const.IMAGE_EXTENSIONS

    @property
    def is_json(self) -> bool:
        return self.suffix == const.MAP_SUFFIX

    @property
    def is_font(self) -> bool:
        return self.suffix in const.FONT_EXTENSIONS

    @property
    def is_audio(self) -> bool:
        return self.suffix in const.AUDIO_EXTENSIONS


@dataclass(slots=True)
class ScanResult:
    """Hasil satu kali pemindaian project.

    Attributes:
        audio: File audio yang ditemukan.
        animations: File config animation yang ditemukan.
        fonts: File font yang ditemukan,
        images: File gambar yang ditemukan.
        json_files: Seluruh file ``.json`` (kandidat map maupun sidecar aset).
        maps: File ``.json`` yang strukturnya menyerupai map.
        other: File lain yang lolos exclude; dipakai tree "tampilkan semua".
        directories: Folder yang benar-benar ditelusuri (relatif, posix).
        pruned: Folder yang dilewati karena ter-exclude.
        cancelled: True bila pemindaian dihentikan sebelum tuntas.
    """

    audio: list[ScanEntry] = field(default_factory=list)
    animations: list[ScanEntry] = field(default_factory=list)
    fonts: list[ScanEntry] = field(default_factory=list)
    images: list[ScanEntry] = field(default_factory=list)
    image_configs: list[ScanEntry] = field(default_factory=list)
    json_files: list[ScanEntry] = field(default_factory=list)
    maps: list[ScanEntry] = field(default_factory=list)
    other: list[ScanEntry] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    cancelled: bool = False

    @property
    def file_count(self) -> int:
        return (
            len(self.images)
            + len(self.json_files)  # sudah mewaliki maps, animations, image_configs
            + len(self.other)
            + len(self.fonts)
            + len(self.audio)
        )


def looks_like(path: Path, *, probe_bytes: int = const.MAP_PROBE_BYTES):
    """Tebak apakah sebuah file JSON adalah map editor.

    Pemeriksaan sengaja dangkal — hanya membaca awal file — karena mem-parse
    seluruh JSON di project besar jauh lebih mahal daripada manfaatnya.

    Args:
        path: File JSON kandidat.
        probe_bytes: Jumlah byte awal yang dibaca.

    Returns:
        True bila strukturnya menyerupai map.
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            head = f.read(probe_bytes)
    except OSError:
        return "other"

    if '"settings"' in head or '"tilesets"' in head or '"map_type"' in head:
        return "map"

    if '"group"' in head or '"animations"' in head:
        return "animation"

    if '"image_path"' in head or '"texture"' in head:
        return "image_config"

    return "other"


def iter_files(
    root: Path,
    rules: ExcludeRules,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_directory: Callable[[str], None] | None = None,
    on_pruned: Callable[[str], None] | None = None,
    follow_symlinks: bool = False,
) -> Iterator[ScanEntry]:
    """Telusuri ``root`` secara iteratif, memangkas folder ter-exclude.

    Folder yang cocok dengan aturan exclude **tidak** dibuka sama sekali, jadi
    biayanya nol alih-alih ditelusuri lalu dibuang.

    Args:
        root: Folder awal.
        rules: Aturan exclude yang sudah dikompilasi.
        should_cancel: Dipanggil per folder; ``True`` menghentikan traversal.
        on_directory: Dipanggil untuk setiap folder yang ditelusuri.
        on_pruned: Dipanggil untuk setiap folder yang dilewati.
        follow_symlinks: Ikuti symlink folder (default tidak, agar aman dari
            siklus).

    Yields:
        :class:`ScanEntry` untuk setiap file yang lolos exclude.
    """
    try:
        base = root.resolve()
    except OSError:
        logger.warning("Root pemindaian tidak dapat dibaca: %s", root)
        return

    if not base.is_dir():
        logger.warning("Root pemindaian bukan folder: %s", base)
        return

    # Stack berisi (path absolut, path relatif posix).
    stack: list[tuple[Path, str]] = [(base, "")]
    seen_dirs: set[str] = set()

    while stack:
        if should_cancel is not None and should_cancel():
            return

        current, relative = stack.pop()
        if on_directory is not None:
            on_directory(relative)

        try:
            with os.scandir(current) as it:
                entries = list(it)
        except (OSError, PermissionError):
            logger.debug("Folder dilewati (tidak terbaca): %s", current, exc_info=True)
            continue

        for entry in entries:
            child_rel = f"{relative}/{entry.name}" if relative else entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
            except OSError:
                continue

            if is_dir:
                if rules.is_excluded_dir(entry.name, child_rel):
                    if on_pruned is not None:
                        on_pruned(child_rel)
                    continue
                if not follow_symlinks:
                    try:
                        real = os.path.realpath(entry.path)
                    except OSError:
                        real = entry.path
                    if real in seen_dirs:
                        continue
                    seen_dirs.add(real)
                stack.append((Path(entry.path), child_rel))
                continue

            try:
                if not entry.is_file(follow_symlinks=follow_symlinks):
                    continue
            except OSError:
                continue
            if rules.is_excluded_dir(entry.name, child_rel):
                if on_pruned is not None:
                    on_pruned(child_rel)
                continue

            yield ScanEntry(
                path=Path(entry.path),
                relative=child_rel,
                suffix=os.path.splitext(entry.name)[1].lower(),
            )


def scan_project(
    root: Path,
    rules: ExcludeRules,
    *,
    should_cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, str], None] | None = None,
    detect_maps: bool = True,
    collect_other: bool = True,
) -> ScanResult:
    """Pindai project sekali jalan untuk gambar, JSON, dan map.

    Args:
        root: Root project.
        rules: Aturan exclude.
        should_cancel: Dipanggil berkala; ``True`` menghentikan pemindaian dan
            menandai hasil sebagai ``cancelled``.
        on_progress: Dipanggil ``(jumlah_file, path_relatif_terakhir)``.
        detect_maps: Jalankan :func:`looks_like_map` pada setiap ``.json``.
        collect_other: Ikut mencatat file bertipe lain (untuk tree lengkap).

    Returns:
        :class:`ScanResult` berisi seluruh temuan.
    """
    result = ScanResult()
    count = 0

    for entry in iter_files(
        root,
        rules,
        should_cancel=should_cancel,
        on_directory=lambda rel: result.directories.append(rel),
        on_pruned=lambda rel: result.pruned.append(rel),
    ):
        if entry.is_image:
            result.images.append(entry)
        elif entry.is_json:
            result.json_files.append(entry)
            look = looks_like(entry.path)
            if look == "animation":
                result.animations.append(entry)
            elif look == "map":
                result.maps.append(entry)
            elif look == "image_config":
                result.image_configs.append(entry)
        elif collect_other:
            result.other.append(entry)

        count += 1
        if on_progress is not None and count % 64 == 0:
            on_progress(count, entry.relative)

    if should_cancel is not None and should_cancel():
        result.cancelled = True

    result.audio.sort(key=lambda e: e.relative.lower())
    result.animations.sort(key=lambda e: e.relative.lower())
    result.fonts.sort(key=lambda e: e.relative.lower())
    result.images.sort(key=lambda e: e.relative.lower())
    result.json_files.sort(key=lambda e: e.relative.lower())
    result.maps.sort(key=lambda p: str(p).lower())
    result.other.sort(key=lambda e: e.relative.lower())

    if on_progress is not None:
        on_progress(count, "")

    # TODO: fix this logging
    logger.info(
        "Scan %s: %d file (%d gambar, %d json, %d map), %d folder dipangkas%s",
        root,
        count,
        len(result.images),
        len(result.json_files),
        len(result.maps),
        len(result.pruned),
        " [dibatalkan]" if result.cancelled else "",
    )
    return result


class ScanState(IntEnum):
    """Status siklus hidup sebuah :class:`ScanJob`."""

    IDLE = auto()
    RUNNING = auto()
    DONE = auto()
    CANCELLED = auto()
    FAILED = auto()


@dataclass(slots=True)
class ScanProgress:
    """Cuplikan progress yang aman ditampilkan UI.

    Attributes:
        files: Jumlah file yang sudah ditemukan.
        current: Path relatif terakhir yang diproses.
        state: Status job saat cuplikan diambil.
    """

    files: int = 0
    current: str = ""
    state: ScanState = ScanState.IDLE

    @property
    def running(self) -> bool:
        return self.state is ScanState.RUNNING


class ScanJob:
    """Pemindaian project yang berjalan di latar belakang.

    Pemakaian dari main thread::

        job = ScanJob(root, rules)
        job.start()
        ...
        result = job.take_result()   # None selama masih berjalan
        if result is not None:
            apply(result)

    Attributes:
        root: Root project yang dipindai.
        rules: Aturan exclude yang dipakai.
    """

    def __init__(
        self,
        root: Path,
        rules: ExcludeRules,
        *,
        on_done: Callable[[ScanResult], None] | None = None,
    ) -> None:
        self.root = root
        self.rules = rules
        self._on_done = on_done

        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._state: ScanState = ScanState.IDLE
        self._files: int = 0
        self._current: str = ""
        self._result: ScanResult | None = None
        self._error: BaseException | None = None
        self._consumed: bool = False

    def start(self) -> bool:
        """Jalankan pemindaian.

        Returns:
            True bila thread berhasil dimulai; False bila job sudah berjalan.
        """
        with self._lock:
            if self._state is ScanState.RUNNING:
                return False
            self._state = ScanState.RUNNING
            self._files = 0
            self._current = ""
            self._result = None
            self._error = None
            self._consumed = False
        self._cancel.clear()

        thread = threading.Thread(
            target=self._run,
            name=f"ryeditor-scan-{self.root.name or 'project'}",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return True

    def cancel(self) -> None:
        """Minta pemindaian berhenti pada kesempatan terdekat."""
        self._cancel.set()

    def shutdown(self, timeout: float = const.JOIN_TIMEOUT) -> None:
        """Batalkan lalu tunggu thread selesai.

        Dipanggil saat aplikasi ditutup; tanpa ini proses dapat menggantung
        karena thread masih menelusuri folder besar.

        Args:
            timeout: Batas tunggu dalam detik.
        """
        self.cancel()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("Thread scan belum berhenti setelah %.1fs", timeout)
        self._thread = None

    @property
    def state(self) -> ScanState:
        with self._lock:
            return self._state

    @property
    def running(self) -> bool:
        return self.state is ScanState.RUNNING

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    @property
    def error(self) -> BaseException | None:
        with self._lock:
            return self._error

    def progress(self) -> ScanProgress:
        """Cuplikan progress terkini (aman dipanggil setiap frame)."""
        with self._lock:
            return ScanProgress(
                files=self._files, current=self._current, state=self._state
            )

    def take_result(self) -> ScanResult | None:
        """Ambil hasil pemindaian satu kali saja.

        Returns:
            :class:`ScanResult` bila pemindaian sudah selesai dan hasilnya belum
            pernah diambil; selain itu ``None``.
        """
        with self._lock:
            if self._result is None or self._consumed:
                return None
            self._consumed = True
            return self._result

    def _report(self, files: int, current: str) -> None:
        with self._lock:
            self._files = files
            self._current = current

    def _run(self) -> None:
        result: ScanResult | None = None
        error: BaseException | None = None
        try:
            result = scan_project(
                self.root,
                self.rules,
                should_cancel=self._cancel.is_set,
                on_progress=self._report,
            )
        except BaseException as exc:
            error = exc
            logger.exception("Pemindaian project gagal: %s", self.root)

        with self._lock:
            self._result = result
            self._error = error
            if error is not None:
                self._state = ScanState.FAILED
            elif result is not None and result.cancelled:
                self._state = ScanState.CANCELLED
            else:
                self._state = ScanState.DONE

        if result is not None and error is None and self._on_done is not None:
            # Callback dijalankan di thread pekerja; pemakai di editor ini hanya
            # memakainya untuk logging. Mutasi state UI tetap lewat take_result.
            try:
                self._on_done(result)
            except Exception:
                logger.exception("Callback on_done pemindaian gagal")


class ScanWorker(plyunit.ServiceUnit):
    def on_attach(self, app: EditorApp):
        self.ctx = app.context
        self.active_job: ScanJob | None = None
        self._scan_reason = None

    def start(self, root: Path, rules: ExcludeRules, *, reason: str = "open"):
        self.cancel()
        self.active_job = ScanJob(root, rules)
        self._scan_reason = reason
        # explorer = self.panel("explorer")
        # if explorer is not None:
        #     explorer.scanning = True
        self.active_job.start()

    def cancel(self):
        """Hentikan pemindaian yang sedang berjalan (bila ada)."""
        if self.active_job is not None:
            self.active_job.shutdown()
            self.active_job = None

    def pool(self):
        job = self.active_job
        project = self.one_or_none("@Project")
        if job is None or project is None:
            return

        result = job.take_result()
        if result is None:
            if job.state is ScanState.FAILED:
                self.ctx.set_status(
                    "Pemindaian project gagal; lihat log.", status=StatusType.ERROR
                )
                self.active_job = None
                # explorer = self.panel("explorer")
                # if explorer is not None:
                #     explorer.scanning = False
            return

        assets = cast(Assets, self.one("@Assets"))
        assets.load_from_scan(result)
        # count = self.project.apply_scan(result)
        # if self.tilesets is not None:
        #     self.tilesets.begin_streaming_load(self.project.assets)
        #     self.tilesets.rebuild_from_index(self.project.assets)

        # Pohon explorer dibangun dari hasil pemindaian yang sama, jadi tidak
        # ada traversal disk kedua dan aturan exclude sudah ikut terterap.
        tree = self.one("@FileTree")
        tree.build(project.get_project_dir().parent, result)

        imgui_layer = self.one("@ImGuiLayer")
        imgui_layer.explorer.set_tree(tree)

        # explorer = self.panel("explorer")
        # if explorer is not None:
        #     explorer.set_tree(tree)
        #     explorer.active_path = (
        #         self.workspace.active.path if self.workspace.active else None
        #     )
        # self._refresh_browsers()
        # self._on_map_changed()
        # self.active_job = None
        verb = "dipindai ulang" if self._scan_reason == "refresh" else "ditemukan"
        self.ctx.set_status(
            f"aset {verb}." + (" (dibatalkan)" if result.cancelled else ""),
            status=StatusType.INFO,
        )

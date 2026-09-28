"""Pohon file project untuk Folder Explorer bergaya VS Code.

:class:`~editor.core.asset_index.AssetIndex` hanya mengenal aset gambar, dan
daftar map hanya berisi ``.json`` yang lolos :func:`~editor.core.scan.looks_like_map`.
Tidak ada satu pun struktur yang menggambarkan **seluruh** isi project seperti
panel Explorer di VS Code, sehingga modul ini menambahkannya.

Sumber datanya adalah :class:`~editor.core.scan.ScanResult` yang sudah dihitung
di thread pekerja: ``images``, ``json_files``, ``other``, dan ``directories``
digabung menjadi satu pohon. Konsekuensinya tidak ada traversal disk kedua, dan
aturan exclude sudah diterapkan sejak pemindaian.

Setiap file diklasifikasi menjadi :class:`FileKind`. Klasifikasi inilah yang
menentukan apa yang terjadi saat file diklik dan file mana yang disembunyikan
oleh toggle "hanya file editor":

* :attr:`FileKind.IMAGE` — buka tab dokumen aset.
* :attr:`FileKind.MAP` — buka tab map.
* :attr:`FileKind.SIDECAR` — konfigurasi aset; diarahkan ke gambar induknya.
* :attr:`FileKind.OTHER` — tidak dapat dibuka editor, hanya ditampilkan.

Pembedaan map vs sidecar tidak dapat dilakukan dari ekstensi saja karena
keduanya ``.json``; :class:`ScanResult` sudah memisahkannya lewat
:func:`~editor.core.scan.looks_like_map`, dan hasil itu yang dipakai di sini.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, cast

from imgui_bundle import icons_fontawesome_6 as icons_fa

import plyunit

if TYPE_CHECKING:
    from .scan import ScanEntry, ScanResult

logger = logging.getLogger(__name__)


class FileKind(Enum):
    """Peran sebuah file di dalam editor.

    Nilainya dipakai sebagai key ikon/urutan di UI, jadi jangan diubah tanpa
    menyesuaikan :data:`KIND_ICONS`.
    """

    IMAGE = "image"
    MAP = "map"
    ANIMATTION = "animation"
    SIDECAR = "sidecar"
    OTHER = "other"
    FONT = "font"
    AUDIO = "audio"

    @property
    def is_openable(self) -> bool:
        """True bila klik pada file ini membuka sebuah tab dokumen.

        Sidecar ikut dihitung karena kliknya diteruskan ke gambar induk.
        """
        return self not in (
            FileKind.OTHER,
            FileKind.ANIMATTION,
            FileKind.AUDIO,
            FileKind.FONT,
        )

    @property
    def is_relevant(self) -> bool:
        """True bila file termasuk yang ditampilkan mode "hanya file editor"."""
        return self is not FileKind.OTHER


KIND_ICONS: dict[FileKind, str] = {
    FileKind.IMAGE: icons_fa.ICON_FA_FILE_IMAGE,
    FileKind.MAP: icons_fa.ICON_FA_MAP,
    FileKind.SIDECAR: icons_fa.ICON_FA_CODE,
    FileKind.OTHER: icons_fa.ICON_FA_FILE_CIRCLE_QUESTION,
    FileKind.ANIMATTION: icons_fa.ICON_FA_FILM,
    FileKind.AUDIO: icons_fa.ICON_FA_FILE_AUDIO,
    FileKind.FONT: icons_fa.ICON_FA_FONT,
}
"""Penanda tekstual per jenis file.

ImGui di sini tidak memakai font ikon, jadi penanda dibuat dari ASCII agar
lebarnya seragam dan nama file tetap sejajar.
"""


@dataclass(slots=True)
class FileEntry:
    """Satu file di dalam pohon explorer.

    Attributes:
        name: Nama file beserta ekstensi.
        path: Path absolut.
        relative: Path relatif terhadap root project, separator posix.
        kind: Klasifikasi peran file.
        asset_id: Asset id bila file ini gambar, atau gambar induk bila file
            ini sidecar. ``None`` untuk jenis lain.
    """

    name: str
    path: Path
    relative: str
    kind: FileKind = FileKind.OTHER
    asset_id: str | None = None

    @property
    def icon(self) -> str:
        return KIND_ICONS[self.kind]

    @property
    def is_openable(self) -> bool:
        """True bila file dapat dibuka sebagai tab.

        Sidecar hanya dapat dibuka bila gambar induknya benar-benar terindeks;
        sidecar yatim tidak mengarah ke mana pun.
        """
        if self.kind is FileKind.SIDECAR:
            return self.asset_id is not None
        return self.kind.is_openable


@dataclass(slots=True)
class DirEntry:
    """Satu folder di dalam pohon explorer.

    Attributes:
        name: Nama folder (``""`` untuk root).
        relative: Path relatif terhadap root project, separator posix.
        children: Sub-folder, terurut berdasarkan nama.
        files: File langsung di dalam folder ini, terurut berdasarkan nama.
    """

    name: str
    relative: str
    children: dict[str, DirEntry] = field(default_factory=dict)
    files: list[FileEntry] = field(default_factory=list)

    def iter_files(self) -> Iterator[FileEntry]:
        """Seluruh file di simpul ini dan turunannya."""
        yield from self.files
        for child in self.children.values():
            yield from child.iter_files()

    def total_files(self, *, relevant_only: bool = False) -> int:
        """Jumlah file di simpul ini dan turunannya.

        Args:
            relevant_only: Hanya hitung file yang dikenal editor.
        """
        if not relevant_only:
            return sum(1 for _ in self.iter_files())
        return sum(1 for f in self.iter_files() if f.kind.is_relevant)

    def has_relevant(self) -> bool:
        """True bila ada minimal satu file yang dikenal editor di bawah simpul.

        Dipakai explorer untuk menyembunyikan folder yang menjadi kosong saat
        toggle "hanya file editor" aktif.
        """
        return any(f.kind.is_relevant for f in self.iter_files())


class FileTree(plyunit.ServiceUnit):
    """Pohon seluruh isi project, dibangun dari hasil pemindaian.

    Attributes:
        root_path: Root folder project.
        root: Simpul akar pohon.
    """

    def __init__(self, root_path: Path = Path()) -> None:
        super().__init__("FileTree", tags={"filetree", "service"})
        self.root_path = root_path
        self.root = DirEntry(name=root_path.name, relative="")
        self._by_relative: dict[str, FileEntry] = {}

    def on_attach(self, app):
        from scripts.services.assets import Assets

        self.assets = cast(Assets, self.one("@Assets"))

    def build(self, root_path: Path, result: ScanResult) -> int:
        """Bangun ulang pohon dari sebuah :class:`ScanResult`.

        Folder kosong yang tercatat di ``result.directories`` tetap dibuat,
        sehingga struktur project terlihat utuh seperti di VS Code — bukan
        hanya folder yang kebetulan berisi file.

        Args:
            result: Hasil pemindaian project.
            assets_root: Basis perhitungan ``asset_id``; default root project.
            known_asset_ids: Asset id yang benar-benar terindeks. Dipakai agar
                sidecar hanya tertaut ke gambar yang ada.

        Returns:
            Jumlah file di dalam pohon.
        """
        self.root_path = root_path
        self.root = DirEntry(name=self.root_path.name, relative="")
        self._by_relative.clear()

        # base = assets_root or self.root_path
        # known = set(known_asset_ids) if known_asset_ids is not None else None

        # Folder didaftarkan lebih dulu agar folder kosong tetap muncul.
        for relative in result.directories:
            self._ensure_dir(relative)

        for entry in result.images:
            self._add_file(entry, FileKind.IMAGE)
        for entry in result.image_configs:
            self._add_file(entry, FileKind.SIDECAR)
        for entry in result.animations:
            self._add_file(entry, FileKind.ANIMATTION)
        for entry in result.fonts:
            self._add_file(entry, FileKind.FONT)
        for entry in result.audio:
            self._add_file(entry, FileKind.AUDIO)
        for entry in result.maps:
            self._add_file(entry, FileKind.MAP)
        for entry in result.other:
            self._add_file(entry, FileKind.OTHER)

        # TODO: sisa dari json yang tidak terdeteksi kemana mana belum di proses
        # for entry in result.json_files:
        #    kind = FileKind.MAP if self._is_map(entry, map_paths) else FileKind.SIDECAR
        #    self._add_file(entry, kind, base=base, known=known)

        self._sort(self.root)
        logger.info("File tree: %d file di %s", len(self._by_relative), self.root_path)
        return len(self._by_relative)

    @staticmethod
    def _is_map(entry: ScanEntry, map_paths: set[Path]) -> bool:
        try:
            return entry.path.resolve() in map_paths
        except OSError:
            return False

    def _ensure_dir(self, relative: str) -> DirEntry:
        """Ambil / buat simpul folder untuk sebuah path relatif."""
        node = self.root
        for part in relative.split("/"):
            if not part:
                continue
            child = node.children.get(part)
            if child is None:
                child_rel = f"{node.relative}/{part}" if node.relative else part
                child = DirEntry(name=part, relative=child_rel)
                node.children[part] = child
            node = child
        return node

    def _add_file(self, entry: ScanEntry, kind: FileKind) -> None:
        parent_rel, _, name = entry.relative.rpartition("/")
        node = self._ensure_dir(parent_rel) if parent_rel else self.root

        asset_id = None
        if kind in (FileKind.IMAGE, FileKind.SIDECAR):
            result = self.assets.get_asset_id_by_path(entry)
            if result is not None:
                asset_id = result

        file_entry = FileEntry(
            name=name or entry.relative,
            path=entry.path,
            relative=entry.relative,
            kind=kind,
            asset_id=asset_id,
        )
        node.files.append(file_entry)
        self._by_relative[entry.relative] = file_entry

    def _sort(self, node: DirEntry) -> None:
        node.children = dict(
            sorted(node.children.items(), key=lambda kv: kv[0].lower())
        )
        node.files.sort(key=lambda f: f.name.lower())
        for child in node.children.values():
            self._sort(child)

    def get(self, relative: str) -> FileEntry | None:
        """Cari file berdasarkan path relatif posix."""
        return self._by_relative.get(relative)

    def directory(self, relative: str) -> DirEntry | None:
        """Cari folder berdasarkan path relatif posix."""
        if not relative:
            return self.root
        node = self.root
        for part in relative.split("/"):
            child = node.children.get(part)
            if child is None:
                return None
            node = child
        return node

    def absolute(self, relative: str) -> Path:
        """Ubah path relatif pohon menjadi absolut."""
        return self.root_path / relative if relative else self.root_path

    @property
    def file_count(self) -> int:
        return len(self._by_relative)

    @property
    def is_empty(self) -> bool:
        return not self._by_relative and not self.root.children

    def search(self, query: str, *, relevant_only: bool = False) -> Sequence[FileEntry]:
        """Cari file berdasarkan substring nama atau path.

        Args:
            query: Substring case-insensitive.
            relevant_only: Batasi pada file yang dikenal editor.

        Returns:
            Daftar file yang cocok, terurut berdasarkan path relatif.
        """
        needle = query.strip().lower()
        out = [
            f
            for f in self.root.iter_files()
            if (not relevant_only or f.kind.is_relevant)
            and (not needle or needle in f.relative.lower())
        ]
        out.sort(key=lambda f: f.relative.lower())
        return out


__all__ = [
    "KIND_ICONS",
    "DirEntry",
    "FileEntry",
    "FileKind",
    "FileTree",
]

"""Pola exclude folder: parsing glob, pencocokan, dan penggabungan berlapis.

Pemindaian project dipandu daftar pola *exclude*. Tanpa itu, ``assets_root``
yang defaultnya ``"."`` membuat editor menelusuri seluruh folder project —
termasuk ``.venv/``, ``.dist/``, dan ``node_modules/`` — sebelum satu frame pun
tampil.

Semantik pola
-------------

Pola adalah glob yang selalu memakai separator posix. Ada dua bentuk:

* **Tanpa ``/``** (mis. ``node_modules``, ``*.egg-info``) — dicocokkan dengan
  *nama* folder pada kedalaman berapa pun.
* **Mengandung ``/``** (mis. ``build/out``) — dicocokkan dengan path relatif
  terhadap root project, dihitung dari root.

``*`` dan ``?`` tidak melewati ``/``; ``**`` melewatinya. Pencocokan tidak peka
huruf besar-kecil agar konsisten di Windows.

Penggabungan berlapis
---------------------

Daftar global berlaku untuk semua project. Bila project menyalakan *override*,
daftar project **mengganti** daftar global sepenuhnya; bila tidak, keduanya
digabung. Di atas hasilnya selalu ditambahkan :data:`ALWAYS_EXCLUDED` yang tidak
dapat dimatikan, agar scaffold editor dan metadata git tidak pernah terpindai.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts import constants as const

logger = logging.getLogger(__name__)

"""Daftar exclude global bawaan."""


def normalize_pattern(raw: Any) -> str:
    """Rapikan satu pola exclude.

    Membuang spasi, mengubah ``\\`` menjadi ``/``, serta melepas ``./`` di awal
    dan ``/`` di akhir sehingga ``build/`` dan ``build`` diperlakukan sama.

    Args:
        raw: Pola mentah dari file config atau input pengguna.

    Returns:
        Pola ternormalisasi; string kosong bila pola tidak dapat dipakai.
    """
    if not isinstance(raw, str):
        return ""
    text = raw.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    text = text.strip("/")
    if text in ("", ".", ".."):
        return ""
    return text


def normalize_patterns(raw: Any) -> tuple[str, ...]:
    """Rapikan daftar pola, buang duplikat, pertahankan urutan.

    Args:
        raw: Iterable pola; nilai non-string dilewati.

    Returns:
        Tuple pola unik yang sudah ternormalisasi.
    """
    if isinstance(raw, str) or not isinstance(raw, (list, tuple, set, frozenset)):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        pattern = normalize_pattern(item)
        if pattern and pattern not in seen:
            seen.add(pattern)
            out.append(pattern)
    return tuple(out)


def _translate(pattern: str) -> str:
    """Ubah pola glob menjadi sumber regex.

    Ditulis manual, bukan memakai :func:`fnmatch.translate`, karena ``fnmatch``
    memperlakukan ``*`` sebagai "apa saja termasuk ``/``" sehingga ``*`` dan
    ``**`` tidak dapat dibedakan.
    """
    out: list[str] = []
    i = 0
    length = len(pattern)
    while i < length:
        char = pattern[i]
        if char == "*":
            if pattern.startswith("**", i):
                i += 2
                if pattern.startswith("/", i):
                    i += 1
                    # "**/" boleh cocok dengan nol folder.
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
            else:
                i += 1
                out.append("[^/]*")
            continue
        if char == "?":
            i += 1
            out.append("[^/]")
            continue
        if char == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                i += 1
                out.append(re.escape("["))
                continue
            body = pattern[i + 1 : end]
            i = end + 1
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append(f"[{body}]")
            continue
        i += 1
        out.append(re.escape(char))
    return "".join(out)


def _compile(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(f"^{_translate(pattern)}$", re.IGNORECASE)
    except re.error:
        logger.warning("Pola exclude '%s' tidak valid, dilewati", pattern)
        return None


@dataclass(frozen=True, slots=True)
class ExcludeRules:
    """Kumpulan pola exclude yang sudah dikompilasi.

    Bersifat immutable dan hashable sehingga dapat dibandingkan untuk mendeteksi
    perubahan setting (dan memicu re-scan) tanpa menyimpan salinan terpisah.

    Attributes:
        patterns: Pola sumber ternormalisasi, untuk ditampilkan di UI.
    """

    patterns: tuple[str, ...] = ()
    _name_res: tuple[re.Pattern[str], ...] = field(
        default=(), repr=False, compare=False, hash=False
    )
    _path_res: tuple[re.Pattern[str], ...] = field(
        default=(), repr=False, compare=False, hash=False
    )

    @classmethod
    def build(cls, patterns: Any) -> ExcludeRules:
        """Kompilasi daftar pola menjadi aturan siap pakai.

        Pola dipisah menjadi dua kelompok: pola berbasis *nama* (tanpa ``/``)
        yang cocok di kedalaman mana pun, dan pola berbasis *path* yang dihitung
        dari root project.

        Args:
            patterns: Iterable pola mentah.

        Returns:
            :class:`ExcludeRules` baru.
        """
        cleaned = normalize_patterns(patterns)
        names: list[re.Pattern[str]] = []
        paths: list[re.Pattern[str]] = []
        for pattern in cleaned:
            compiled = _compile(pattern)
            if compiled is None:
                continue
            if "/" in pattern:
                paths.append(compiled)
            else:
                names.append(compiled)
        return cls(
            patterns=cleaned,
            _name_res=tuple(names),
            _path_res=tuple(paths),
        )

    @property
    def is_empty(self) -> bool:
        return not self._name_res and not self._path_res

    def is_excluded_dir(self, name: str, relative_path: str) -> bool:
        """True bila sebuah folder harus dilewati.

        Args:
            name: Nama folder itu sendiri.
            relative_path: Path folder relatif terhadap root project.

        Returns:
            True bila folder cocok dengan salah satu pola.
        """
        if any(regex.match(name) for regex in self._name_res):
            return True
        candidate = normalize_pattern(relative_path)
        if not candidate:
            return False
        return any(regex.match(candidate) for regex in self._path_res)

    def is_excluded_relative(self, relative_path: str) -> bool:
        """True bila path relatif atau salah satu induknya ter-exclude."""
        candidate = normalize_pattern(relative_path)
        if not candidate:
            return False
        parts = candidate.split("/")
        for i in range(len(parts)):
            if self.is_excluded_dir(parts[i], "/".join(parts[: i + 1])):
                return True
        return False

    def is_excluded_path(self, path: Path, root: Path) -> bool:
        """True bila ``path`` berada di dalam sesuatu yang ter-exclude.

        Path di luar ``root`` dianggap tidak ter-exclude: aturan ini hanya
        berbicara tentang isi project.

        Args:
            path: Path absolut yang diperiksa.
            root: Root project.
        """
        try:
            relative = Path(path).relative_to(root).as_posix()
        except ValueError:
            return False
        return self.is_excluded_relative(relative)


def resolve_excludes(
    global_patterns: Any,
    project_patterns: Any = None,
    *,
    override: bool = True,
) -> ExcludeRules:
    """Gabungkan daftar global dan project menjadi satu aturan.

    Args:
        global_patterns: Pola dari config global.
        project_patterns: Pola dari ``project.json``.
        override: Bila True (default), daftar project **mengganti** daftar
            global saat project punya minimal satu pola. Bila False, keduanya
            digabung.

    Returns:
        :class:`ExcludeRules` gabungan, selalu memuat :data:`ALWAYS_EXCLUDED`.
    """
    globals_ = normalize_patterns(global_patterns)
    project = normalize_patterns(project_patterns)

    if project and override:
        base: tuple[str, ...] = project
    else:
        base = (*globals_, *project)
    return ExcludeRules.build((*base, *const.ALWAYS_EXCLUDED))

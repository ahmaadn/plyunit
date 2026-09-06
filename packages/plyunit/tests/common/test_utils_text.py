from __future__ import annotations

from plyunit.utils.text import bstr


def test_bstr_converts_str_and_preserves_bytes() -> None:
    assert bstr("hello") == b"hello"

    raw = b"payload"
    assert bstr(raw) is raw

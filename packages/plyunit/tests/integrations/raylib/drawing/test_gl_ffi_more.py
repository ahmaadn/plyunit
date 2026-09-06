from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.gl_ffi as gl_ffi


def test_get_gl_func_glfw_fallback(monkeypatch: pytest.MonkeyPatch):
    gl_ffi.reset_gl_funcs()
    addr = object()

    def fail_rl(name):
        raise RuntimeError("no")

    monkeypatch.setattr(gl_ffi.pr, "rl_get_proc_address", fail_rl, raising=False)
    monkeypatch.setattr(
        gl_ffi.pr,
        "glfw_get_proc_address",
        lambda name: addr,
        raising=False,
    )
    monkeypatch.setattr(
        gl_ffi.pr,
        "ffi",
        SimpleNamespace(NULL=None, cast=lambda s, a: lambda *x: "ok"),
        raising=False,
    )
    fn = gl_ffi.get_gl_func("glFoo", "void(*)()")
    assert fn() == "ok"
    # cached
    assert gl_ffi.get_gl_func("glFoo", "void(*)()") is fn
    gl_ffi.reset_gl_funcs()


def test_get_gl_func_missing(monkeypatch: pytest.MonkeyPatch):
    gl_ffi.reset_gl_funcs()
    monkeypatch.setattr(
        gl_ffi.pr, "rl_get_proc_address", lambda n: None, raising=False
    )
    monkeypatch.setattr(
        gl_ffi.pr, "glfw_get_proc_address", lambda n: None, raising=False
    )
    monkeypatch.setattr(
        gl_ffi.pr, "ffi", SimpleNamespace(NULL=None), raising=False
    )
    with pytest.raises(RuntimeError):
        gl_ffi.get_gl_func("glMissing", "void(*)()")

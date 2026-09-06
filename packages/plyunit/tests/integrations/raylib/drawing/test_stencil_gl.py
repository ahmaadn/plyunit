from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.gl_ffi as gl_ffi
import plyunit.backends.integrations.raylib.drawing.stencil as stencil_mod


@pytest.fixture()
def gl_env(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple] = []
    depth_on = [1]

    def make_fn(name: str):
        def _fn(*args):
            calls.append((name, args))
            if name == "glIsEnabled":
                return depth_on[0]
            return None

        return _fn

    funcs = {
        "glEnable": make_fn("glEnable"),
        "glDisable": make_fn("glDisable"),
        "glIsEnabled": make_fn("glIsEnabled"),
        "glClear": make_fn("glClear"),
        "glClearStencil": make_fn("glClearStencil"),
        "glStencilFunc": make_fn("glStencilFunc"),
        "glStencilOp": make_fn("glStencilOp"),
        "glStencilMask": make_fn("glStencilMask"),
        "glColorMask": make_fn("glColorMask"),
    }

    monkeypatch.setattr(gl_ffi, "_gl_funcs", dict(funcs))
    monkeypatch.setattr(gl_ffi, "get_gl_func", lambda name, sig: funcs[name])
    monkeypatch.setattr(stencil_mod, "get_gl_func", lambda name, sig: funcs[name])
    monkeypatch.setattr(stencil_mod, "flush_render_batch", lambda: calls.append(("flush",)))
    stencil_mod.reset_stencil()
    stencil_mod._initialized = True
    return calls, depth_on


def test_stencil_mask_cycle(gl_env):
    calls, _ = gl_env
    stencil_mod.begin_stencil_mask()
    assert stencil_mod.is_stencil_active() is True
    assert any(c[0] == "glEnable" for c in calls)
    assert any(c[0] == "glColorMask" and c[1] == (0, 0, 0, 0) for c in calls)

    stencil_mod.end_stencil_mask()
    assert any(
        c[0] == "glStencilFunc" and c[1][0] == stencil_mod.GL_EQUAL for c in calls
    )

    stencil_mod.end_stencil_mode()
    assert stencil_mod.is_stencil_active() is False
    assert any(c[0] == "glDisable" for c in calls)


def test_stencil_mask_inverse(gl_env):
    calls, _ = gl_env
    stencil_mod.begin_stencil_mask()
    stencil_mod.end_stencil_mask_inverse()
    assert any(
        c[0] == "glStencilFunc" and c[1][0] == stencil_mod.GL_NOTEQUAL for c in calls
    )
    stencil_mod.end_stencil_mode()


def test_stencil_restores_depth(gl_env):
    calls, depth_on = gl_env
    depth_on[0] = 1
    stencil_mod.begin_stencil_mask()
    assert any(c[0] == "glDisable" and c[1][0] == stencil_mod.GL_DEPTH_TEST for c in calls)
    stencil_mod.end_stencil_mode()
    assert any(c[0] == "glEnable" and c[1][0] == stencil_mod.GL_DEPTH_TEST for c in calls)


def test_gl_ffi_reset_and_has(monkeypatch: pytest.MonkeyPatch):
    gl_ffi.reset_gl_funcs()
    assert gl_ffi.has_gl_func("glEnable") is False
    fake = object()
    monkeypatch.setattr(
        gl_ffi.pr, "rl_get_proc_address", lambda n: fake, raising=False
    )
    monkeypatch.setattr(
        gl_ffi.pr,
        "ffi",
        SimpleNamespace(NULL=None, cast=lambda s, a: lambda *x: None),
        raising=False,
    )
    gl_ffi.get_gl_func("glEnable", "void(*)(unsigned int)")
    assert gl_ffi.has_gl_func("glEnable")
    gl_ffi.flush_render_batch()
    gl_ffi.reset_gl_funcs()

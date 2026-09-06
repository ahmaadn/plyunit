from __future__ import annotations

from types import SimpleNamespace

import pytest

import plyunit.backends.integrations.raylib.drawing.gl_ffi as gl_ffi
import plyunit.backends.integrations.raylib.drawing.stencil as stencil_mod
from plyunit.rendering.draw_scope import DrawScope
import plyunit.backends.integrations.raylib.drawing.canvas as Canvas


def test_canvas_stencil_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    import plyunit.backends.integrations.raylib.drawing.canvas as Canvas

    calls: list[str] = []
    monkeypatch.setattr(
        Canvas, "init_stencil", lambda: calls.append("init") or True
    )
    monkeypatch.setattr(
        Canvas, "begin_stencil_mask", lambda: calls.append("begin")
    )
    monkeypatch.setattr(Canvas, "end_stencil_mask", lambda: calls.append("end"))
    monkeypatch.setattr(
        Canvas, "end_stencil_mask_inverse", lambda: calls.append("end_inv")
    )
    monkeypatch.setattr(
        Canvas, "end_stencil_mode", lambda: calls.append("mode_off")
    )

    assert Canvas.init_stencil() is True
    Canvas.begin_stencil_mask()
    Canvas.end_stencil_mask()
    Canvas.end_stencil_mask_inverse()
    Canvas.end_stencil_mode()
    assert calls == ["init", "begin", "end", "end_inv", "mode_off"]


def test_draw_scope_stencil_session() -> None:
    events: list[str] = []

    class FakeCanvas:
        def begin_stencil_mask(self) -> None:
            events.append("begin")

        def end_stencil_mask(self) -> None:
            events.append("end")

        def end_stencil_mask_inverse(self) -> None:
            events.append("end_inv")

        def end_stencil_mode(self) -> None:
            events.append("mode_off")

        def draw_circle(self, **kwargs) -> None:
            events.append("circle")

        def draw_rectangle(self, **kwargs) -> None:
            events.append("rect")

    renderer = SimpleNamespace(canvas=FakeCanvas(), _immediate_active=True)
    # pyrefly: ignore [bad-argument-type]
    draw = DrawScope(renderer)

    with draw.stencil() as st:
        with st.mask():
            draw.circle(10, 10, 5)
        draw.rect((0, 0, 20, 20), (255, 0, 0, 255))

    assert events == ["begin", "circle", "end", "rect", "mode_off"]
    assert draw._stencil_active is False


def test_draw_scope_stencil_inverse() -> None:
    events: list[str] = []

    class FakeCanvas:
        def begin_stencil_mask(self) -> None:
            events.append("begin")

        def end_stencil_mask(self) -> None:
            events.append("end")

        def end_stencil_mask_inverse(self) -> None:
            events.append("end_inv")

        def end_stencil_mode(self) -> None:
            events.append("mode_off")

        def draw_circle(self, **kwargs) -> None:
            events.append("circle")

    renderer = SimpleNamespace(canvas=FakeCanvas(), _immediate_active=True)
    # pyrefly: ignore [bad-argument-type]
    draw = DrawScope(renderer)

    with draw.stencil(inverse=True) as st:
        with st.mask():
            draw.circle(0, 0, 1)

    assert events == ["begin", "circle", "end_inv", "mode_off"]


def test_draw_scope_stencil_force_reset() -> None:
    events: list[str] = []

    class FakeCanvas:
        def begin_stencil_mask(self) -> None:
            events.append("begin")

        def end_stencil_mask(self) -> None:
            events.append("end")

        def end_stencil_mode(self) -> None:
            events.append("mode_off")

        def draw_circle(self, **kwargs) -> None:
            pass

    renderer = SimpleNamespace(canvas=FakeCanvas(), _immediate_active=True)
    # pyrefly: ignore [bad-argument-type]
    draw = DrawScope(renderer)
    # pyrefly: ignore [missing-attribute]
    draw.canvas.begin_stencil_mask()
    draw._stencil_active = True
    draw.force_reset()
    assert events == ["begin", "mode_off"]
    assert draw._stencil_active is False


def test_draw_scope_stencil_usable_without_immediate_flag() -> None:
    """DrawScope is a canvas helper; no immediate-phase gate."""
    events: list[str] = []

    class FakeCanvas:
        def begin_stencil_mask(self) -> None:
            events.append("begin")

        def end_stencil_mask(self) -> None:
            events.append("end")

        def end_stencil_mode(self) -> None:
            events.append("mode_off")

    renderer = SimpleNamespace(canvas=FakeCanvas())
    draw = DrawScope(renderer)
    with draw.stencil() as session:
        with session.mask():
            pass
    assert "begin" in events
    assert "end" in events


def test_stencil_init_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    stencil_mod.reset_stencil()
    gl_ffi.reset_gl_funcs()

    fake_addr = object()
    monkeypatch.setattr(
        gl_ffi.pr, "rl_get_proc_address", lambda name: fake_addr, raising=False
    )
    monkeypatch.setattr(
        gl_ffi.pr,
        "ffi",
        SimpleNamespace(
            NULL=None,
            cast=lambda signature, addr: lambda *a, **k: None,
        ),
        raising=False,
    )

    assert stencil_mod.init_stencil() is True
    assert stencil_mod.is_stencil_available() is True
    assert stencil_mod.init_stencil() is True

    stencil_mod.reset_stencil()
    gl_ffi.reset_gl_funcs()

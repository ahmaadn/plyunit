"""Application root unit for plyunit games.

Provides :class:`App`, the ``ServiceUnit`` singleton that owns the main loop,
lifecycle signals, fixed-step scheduling, and shutdown orchestration, plus the
``AppConfig``/``AudioConfig``/``ImGuiConfig``/``PhysicsConfig`` re-exports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from plyunit.core.logging import configure_logging
from plyunit.core.units.service_unit import ServiceUnit
from plyunit.events.signal import Signal

from .schema_config import (
    AppConfig,
    AudioConfig,
    ImGuiConfig,
    PhysicsConfig,
)

if TYPE_CHECKING:
    from plyunit.assets import Animations, Assets
    from plyunit.backends.integrations import Camera2D
    from plyunit.backends.interfaces.i_renderer import ICanvas2D, IWindow
    from plyunit.core.units.service_unit import ServiceUnit
    from plyunit.rendering.renderer import Renderer
    from plyunit.services.scene_manager import SceneManager

__all__ = (
    "App",
    "AppConfig",
    "AudioConfig",
    "ImGuiConfig",
    "PhysicsConfig",
)

logger = logging.getLogger(__name__)


class App(ServiceUnit):
    """Service root of a 2D game application.

    Manages window configuration, the time loop, lifecycle signals, and
    event bus routing. ``App`` is a ``ServiceUnit`` that runs as a global
    singleton (tag ``app``).
    """

    def __init__(self) -> None:
        """Initialize ``App`` with lifecycle signals and empty internal state.

        Signals emitted:
            - ``on_load_complete``: after ``on_load()`` finishes.
            - ``on_start_frame``: at the start of every frame.
            - ``on_end_frame``: at the end of every frame.
            - ``on_init_complete``: after ``init()`` finishes.
            - ``on_begin_update`` / ``on_end_update``: around each fixed step.
            - ``on_after_update``: once per substep, after ``fixed_update``
              returns.
            - ``on_fixed_update``: once per substep, after the step is fully
              done (physics, tween, and timer services).
        """
        self._is_app_root = True
        super().__init__("App", tags={"app"})
        self.running: bool = False

        # Signal
        self.on_load_complete = Signal("on_app_load_complete")
        self.on_start_frame = Signal("on_app_start_frame")
        self.on_end_frame = Signal("on_app_end_frame")
        self.on_init_complete = Signal("on_app_init_complete")
        self.on_fixed_update = Signal("on_app_fixed_update")
        self.on_begin_update = Signal("on_app_begin_update")
        self.on_after_update = Signal("on_app_after_update")
        self.on_end_update = Signal("on_app_end_update")

        # Services — populated by ``init`` (or manually).
        # pyrefly: ignore [bad-assignment]
        self.config: AppConfig = None
        self.window: IWindow = None
        self.canvas: ICanvas2D = None
        self.renderer: Renderer = None
        self.scene_manager: SceneManager = None
        self.assets: Assets = None
        self.animations: Animations = None
        # initialized at load time, since it may need access to the scene
        # or other units
        self.camera: Camera2D | None = None

        self._shutdown_done = False

        # Fixed-step catch-up bookkeeping (set each wall-clock frame).
        self._last_fixed_steps: int = 0
        self._fixed_step_index: int = 0
        # cumulative fixed-step counter (never resets). Useful for stats
        # overlays / correlating frame_profile windows across substeps.
        self._fixed_step_count: int = 0

    @property
    def fixed_step_index(self) -> int:
        """Index of the current fixed substep within a wall-clock frame (``0..N-1``).

        Used to gate one-shot input so it only runs on the first substep,
        etc.
        """
        return self._fixed_step_index

    @property
    def fixed_step_count(self) -> int:
        """Cumulative number of fixed steps run since the ``App`` started.

        Useful for stats overlays and correlating across substeps.
        """
        return self._fixed_step_count

    @property
    def is_first_fixed_step(self) -> bool:
        """``True`` only for the first substep of the current wall-clock frame.

        One-shot input (pressed / released / repeat) must be gated on this,
        or use the Mouse/Keyboard edges, which are already automatic. Level
        input (``is_down``) remains valid on every substep.
        """
        return self._fixed_step_index == 0

    def init(
        self,
        config: str | AppConfig | None = None,
    ):
        """Applies configuration to the window clock and (optionally) logging.

        The signature still accepts ``config`` for backward compatibility
        with subclasses that still call ``self.init(...)``.

        Args:
            config: Configuration file path, an ``AppConfig`` instance, or
                ``None`` to use defaults.
        """
        if isinstance(config, AppConfig):
            self.config = config
        elif isinstance(config, str):
            self.config = AppConfig.from_file(config)
        else:
            self.config = AppConfig()

        if self.window is not None:
            self.window.init_window(
                self.config.window_width,
                self.config.window_height,
                self.config.title,
            )
            self.window.begin_drawing()
            self.window.clear_background(self.config.background_color)
            self.window.end_drawing()

            if self.renderer is not None:
                self.renderer.init()

            if self.config.target_fps > 0:
                self.window.set_target_fps(self.config.target_fps)

        if self.window is not None:
            self.window.set_fixed_timestep_hz(self.config.fixed_update_hz)
            self.window.max_frame_delta_time = self.config.max_frame_delta_time

        # Optional logging — only when a file path is given
        if self.config.log_file_path is not None:
            self.setup_logging(self.config.log_level, self.config.log_file_path)

        # Set max_frame_delta_time from config
        self.on_init_complete.emit()

    def on_load(self) -> None:
        """Called when the application starts, before the update loop begins.

        Override to initialize application-level state.
        """
        pass

    def on_unload(self) -> None:
        """Called once when the application shuts down, before services are released.

        Override to save state and free application-owned resources that
        still require an active graphics context.
        """

    def quit(self) -> None:
        """Asks the main loop to stop cleanly at the end of the current iteration."""
        self.running = False

    def run(self) -> None:
        """Run the main loop until ``running`` becomes ``False``.

        Each iteration runs ``_start_frame`` → ``step_fixed()`` →
        ``update(dt)`` → ``end_frame``. The engine owns frame timing and
        fixed-step scheduling only — everything inside the two mandatory
        hooks (:meth:`fixed_update` and :meth:`update`) is the user's
        responsibility, including the whole render pipeline
        (``SceneManager.update``/``apply_pending``, ``Camera2D``,
        ``Renderer``, ``Window.begin_drawing``/``end_drawing``).

        Raises:
            RuntimeError: If ``AppConfig`` is not set (call ``init``
                before ``run``).
        """
        if self.config is None:
            raise RuntimeError(
                "AppConfig must be set before running the app (call init)"
            )

        loop_error: BaseException | None = None
        try:
            self.on_load()
            self.on_load_complete.emit()
            self.running = True
            while self.running and not (
                self.window is not None and self.window.window_should_close()
            ):
                self._start_frame()
                self.step_fixed()
                frame_dt = self.window.dt if self.window is not None else 0.0
                self.update(frame_dt)
                self._end_frame()
        except BaseException as exc:
            loop_error = exc
            raise
        finally:
            try:
                self.shutdown()
            except BaseException:
                if loop_error is None:
                    raise
                logger.exception(
                    "App shutdown failed after an earlier application error"
                )

    def shutdown(self) -> None:
        """Releases all runtime resources owned by the application exactly once.

        The teardown order keeps GPU resources owning their context: scenes,
        application hooks, optional services, animations/assets, renderer/UBR,
        then the window. Every stage is still attempted if one stage fails;
        the first cleanup error is raised after cleanup finishes.
        """
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self.running = False
        failures: list[BaseException] = []

        def cleanup(label: str, callback) -> None:
            """Run one shutdown step, recording failures instead of aborting."""
            try:
                callback()
            except BaseException as exc:
                failures.append(exc)
                logger.exception("App shutdown step failed: %s", label)

        if self.scene_manager is not None:
            cleanup("scenes", self.scene_manager.shutdown)

        cleanup("app.on_unload", self.on_unload)

        for svc in self.global_units.services_for_app(self):
            cleanup(
                f"service {svc.name}",
                lambda svc=svc: self.global_units.unregister(svc),
            )

        if self.animations is not None:
            cleanup("animations", self.animations.clear)
        if self.assets is not None:
            cleanup("assets", self.assets.clear_all)
        if self.renderer is not None:
            cleanup("renderer", self.renderer.shutdown)
        if self.window is not None:
            cleanup("window", self.window.close_window)

        # Release direct service fields after hooks and resource cleanup. The
        # registry is the sole owner for query-located services.
        self.window = None
        self.canvas = None
        self.scene_manager = None
        self.animations = None
        self.assets = None
        self.renderer = None
        self.camera = None
        self.global_units.unregister(self)

        if failures:
            raise failures[0]

    def destroy(self) -> None:
        """Destroy the app through the full shutdown contract."""
        self.shutdown()

    def _start_frame(self) -> None:
        """Hook internal: advance the window clock and emit ``on_start_frame``."""
        if self.window is not None:
            self.window.start_frame()
        self.on_start_frame.emit()

    def _end_frame(self) -> None:
        """Internal hook: emit ``on_end_frame`` at the end of every frame."""
        self.on_end_frame.emit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def step_fixed(self) -> int:
        """Run 0..N fixed substeps, consuming the accumulator from ``Window``.

        Each substep runs the internal :meth:`_fixed_step` orchestration,
        which calls the mandatory user hook :meth:`fixed_update`.

        Returns:
            int: Number of fixed steps executed this frame.
        """
        if self.config is None or self.window is None:
            return 0
        fixed_steps = self.window.consume_fixed_steps(
            self.config.max_substeps_per_frame
        )
        self._last_fixed_steps = fixed_steps
        dt = self.window.fixed_delta_time
        for i in range(fixed_steps):
            self._fixed_step_index = i
            self._fixed_step_count += 1
            self._fixed_step(dt, i)
        self._fixed_step_index = 0
        return fixed_steps

    def _fixed_step(self, dt: float, step: int) -> None:
        """Internal: one fixed tick around the user's ``fixed_update`` hook.

        Order per substep: ``SceneManager.begin_step`` (bookkeeping) →
        ``on_begin_update`` → EventBus dispatch → :meth:`fixed_update` (user
        hook) → ``on_after_update`` → ``on_end_update`` → ``on_fixed_update``
        → EventBus dispatch → ``SceneManager.end_step``.

        ``SceneManager.update(dt)`` and ``SceneManager.apply_pending()`` are
        NOT called here — the user calls them from ``fixed_update``.
        """
        if self.scene_manager is not None:
            self.scene_manager.begin_step()
        try:
            self.on_begin_update.emit(dt)
            self._dispatch_event_bus()
            self.fixed_update(dt, step)
            self.on_after_update.emit(dt)
            self.on_end_update.emit(dt)
            self.on_fixed_update.emit(dt)
            self._dispatch_event_bus()
        finally:
            if self.scene_manager is not None:
                self.scene_manager.end_step()

    def fixed_update(self, dt: float, step: int) -> None:
        """Mandatory user hook: one fixed substep of deterministic simulation.

        The engine guarantees when this runs (once per fixed substep, inside
        ``SceneManager.begin_step``/``end_step`` bookkeeping) but never what
        happens inside. The typical implementation drives the scene tree:

        .. code-block:: python

            def fixed_update(self, dt: float, step: int) -> None:
                self.scene_manager.update(dt)
                self.scene_manager.apply_pending()

        If the user never calls ``SceneManager.apply_pending()``, queued
        scene transitions (``push``/``pop``) are simply never applied.

        Args:
            dt: Fixed delta time in seconds.
            step: Index of this substep within the wall-clock frame (``0..N-1``).
        """

    def _dispatch_event_bus(self) -> None:
        """Internal hook: call ``EventBus.dispatch()`` if available."""
        bus = self.one_or_none("@EventBus", scope="global")
        if bus is None:
            return
        bus.dispatch()

    def setup_logging(self, log_level: str, log_file_path: str) -> None:
        """Configures logging via :func:`configure_logging`.

        Args:
            log_level: Log level (e.g. ``"INFO"``).
            log_file_path: Destination log file path.
        """
        configure_logging(log_level, log_file_path)

    def update(self, dt: float) -> None:
        """Mandatory user hook: once per frame, after all fixed substeps.

        The engine only guarantees the call timing (once per frame, after
        ``step_fixed()`` and before ``on_end_frame``). The render pipeline is
        entirely user-owned; a typical implementation:

        .. code-block:: python

            def update(self, dt: float) -> None:
                self.camera.update(self.window.unscaled_dt)
                self.renderer.reset_frame()
                self.window.begin_drawing()
                self.window.clear_background(self.config.background_color)
                self.scene_manager.render(self.renderer)
                self.renderer.flush_all(camera=self.camera)
                self.window.end_drawing()

        There is no default render fallback: if this hook does not render,
        nothing is rendered.

        Args:
            dt: Scaled frame delta time in seconds (``window.dt``).
        """

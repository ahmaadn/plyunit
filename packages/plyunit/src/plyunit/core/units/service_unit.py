"""``ServiceUnit``: base class for global singleton services attached to an App."""

from __future__ import annotations

import functools
from typing import Any

from .unit import Unit


class ServiceUnit(Unit):
    """Base class for global singleton services.

    A service is a ``Unit`` with ``singleton_kind == "service"`` that is
    registered and held by the global registry. Services attach to the
    active App after their constructor finishes and are retrieved via
    an ``@Name`` query.
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        tags: set[str] | None = None,
    ) -> None:
        """Initialize a service singleton with ``singleton_kind="service"``.

        Args:
            name: Service name (``None`` → class name).
            tags: Initial set of tags.
        """
        self._service_init_complete = False
        self._attached_app: Any | None = None
        super().__init__(name, is_unique=True, tags=tags, unit_kind="service")
        if type(self) is ServiceUnit:
            self._finish_service_init()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Finalize service construction after subclass fields are initialized."""
        super().__init_subclass__(**kwargs)
        original_init = cls.__dict__.get("__init__")
        # A direct ServiceUnit subclass without its own constructor still needs
        # a finalization point. A deeper subclass inherits an already wrapped
        # constructor and must keep that constructor's behavior.
        if original_init is None:
            if cls.__init__ is not ServiceUnit.__init__:
                return
            original_init = ServiceUnit.__init__
        if getattr(original_init, "_plyunit_service_wrapper", False):
            return

        @functools.wraps(original_init)
        def wrapped_init(self, *args: Any, **init_kwargs: Any) -> None:
            """Run the original __init__, finalizing the service at depth 0."""
            if not hasattr(self, "_service_init_depth"):
                self._service_init_depth = 0
            self._service_init_depth += 1
            completed = False
            try:
                original_init(self, *args, **init_kwargs)
                completed = True
            finally:
                self._service_init_depth -= 1
                if self._service_init_depth == 0:
                    if completed:
                        try:
                            self._finish_service_init()
                        except BaseException:
                            registry = getattr(self, "global_units", None)
                            if registry is not None:
                                registry.unregister(self)
                            raise
                    else:
                        registry = getattr(self, "global_units", None)
                        if registry is not None:
                            registry.unregister(self)

        wrapped_init._plyunit_service_wrapper = True  # type: ignore[attr-defined]
        cls.__init__ = wrapped_init  # type: ignore[method-assign]

    def _finish_service_init(self) -> None:
        """Finalize service initialization once construction completes."""
        # A subclass that skips ServiceUnit.__init__ (e.g. an engine-free test
        # double) was never registered as a service; there is nothing to
        # finalize.
        if not hasattr(self, "_service_init_complete"):
            return
        if self._service_init_complete:
            return
        self._service_init_complete = True
        if getattr(self, "_is_app_root", False):
            self.global_units.activate_app(self)
        else:
            self.global_units._service_ready(self)

    def _attach_to_app(self, app: Any) -> None:
        """Attach this service to the given App via :meth:`on_attach`.

        Args:
            app: App instance to attach to.

        Raises:
            RuntimeError: If the service is already attached to another app.
        """
        if self._attached_app is app:
            return
        if self._attached_app is not None:
            raise RuntimeError(f"Service {self.name!r} is already attached to an app")
        self.on_attach(app)
        if self._attached_app is None:
            self._attached_app = app

    def _detach_from_app(self, app: Any) -> None:
        """Detach this service from the given App via :meth:`on_detach`.

        Args:
            app: App instance to detach from.
        """
        if self._attached_app is not app:
            return
        self.on_detach(app)
        if self._attached_app is app:
            self._attached_app = None

    def on_attach(self, app: Any) -> None:
        """Lifecycle hook: called when the service finishes creation with an active App.

        Override to wire the service into the ``App`` (e.g. cache renderer
        references, read config, etc.).

        Args:
            app: The ``App`` instance hosting this service.
        """

    def on_detach(self, app: Any) -> None:
        """Lifecycle hook: called when the service is removed from the active App.

        Override to clean up resources.

        Args:
            app: The ``App`` instance hosting this service.
        """

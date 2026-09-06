"""Registry of backends known to plyunit."""

INTEGRATION_BACKENDS = ("raylib",)
"""Tuple of known integration backend names (e.g. ``"raylib"``)."""

PHYSICS_BACKENDS = ("pymunk",)
"""Tuple of known physics backend names (e.g. ``"pymunk"``)."""

IMGUI_BACKENDS = ("raylib",)  # auto-follow integration backend
"""Tuple of ImGui backend names (follows the integration backend)."""

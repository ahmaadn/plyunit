"""Internal plyunit configuration based on environment variables.

This module reads runtime settings from ``os.environ`` at first import. The
resulting values are used by other modules (especially ``backends/_selector``)
to select the appropriate backend.

Recognized environment variables:
    PLYUNIT_BACKEND       Active renderer backend (currently only ``"raylib"``).
    PLYUNIT_PHYSICS       Active physics backend (currently only ``"pymunk"``).
    PLYUNIT_BUILD_NATIVE  Build native binaries at import time
        (``"1"``/``"true"``/``"yes"``/``"on"``).

Unknown values fall back to defaults, so this module always provides valid
values.
"""

import os

#: Active renderer backend. Currently only ``"raylib"`` is supported; any other
#: value is reset to ``"raylib"`` to prevent downstream errors.
BACKEND = os.environ.get("PLYUNIT_BACKEND", "raylib")

#: Active physics backend. Currently only ``"pymunk"`` is supported; any other
#: value is reset to ``"pymunk"``.
PHYSICS_BACKEND = os.environ.get("PLYUNIT_PHYSICS", "pymunk")

#: Native build flag. ``True`` when the environment requests building binaries
#: (``"1"``, ``"true"``, ``"yes"``, ``"on"``); ``False`` for any other value.
NATIVE_BUILD = os.environ.get("PLYUNIT_BUILD_NATIVE", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

if BACKEND not in {"raylib"}:
    BACKEND = "raylib"
if PHYSICS_BACKEND not in {"pymunk"}:
    PHYSICS_BACKEND = "pymunk"

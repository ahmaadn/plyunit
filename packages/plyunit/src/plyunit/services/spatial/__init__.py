"""``SpatialIndex`` service (hash-grid based spatial index).

Opt in via ``SpatialIndex()``. Supports incremental refresh (default) and
full rebuild (debug/teleport). See ``plyunit.services.spatial.spatial_index``
for the implementation.
"""

from .spatial_index import SpatialIndex

__all__ = ["SpatialIndex"]

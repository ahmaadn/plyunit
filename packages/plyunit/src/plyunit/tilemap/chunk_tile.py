"""ChunkTile — manages loading/unloading of visible chunks with a simple LRU policy."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from .map_data import ChunkKey

if TYPE_CHECKING:
    from .tilemap import TileMapNode


class ChunkTile:
    """Active-chunk manager for :class:`TileMapNode`.

    Manages loading/unloading of visible chunks with a simple margin and
    maximum-capacity policy (LRU). Supports a ``pin_all`` mode for small
    maps so every chunk stays loaded at once.

    Attributes:
        loaded: Set of chunk keys currently loaded.
        max_loaded: Maximum capacity of chunks pinned in memory.
        margin: Margin of chunks around the viewport that stay loaded.
        max_loads_per_update: Limit on how many chunks may be loaded per
            ``update`` call (``0`` means no limit).
    """

    def __init__(
        self,
        tilemap: TileMapNode,
        max_loaded: int = 64,
        margin: int = 1,
        max_loads_per_update: int = 0,
    ) -> None:
        """Initializes the chunk manager.

        Args:
            tilemap: The tilemap node whose chunks will be managed.
            max_loaded: Maximum capacity of active chunks (``>= 1``).
            margin: Chunk margin around the viewport (``>= 0``).
            max_loads_per_update: Load limit per ``update`` call (``>= 0``).
        """
        self._tilemap = tilemap
        self._max_loaded = max(1, int(max_loaded))
        self._margin = max(0, int(margin))
        self._max_loads_per_update = max(0, int(max_loads_per_update))
        self._loaded: OrderedDict[ChunkKey, None] = OrderedDict()

    @property
    def loaded(self) -> set[ChunkKey]:
        """Gets the set of chunk keys currently active.

        Returns:
            set[ChunkKey]: Snapshot of the currently loaded chunk keys.
        """
        return set(self._loaded)

    def is_loaded(self, key: ChunkKey) -> bool:
        """Checks whether the chunk with the given key is loaded.

        Args:
            key: The chunk key (format ``"cx,cy"``).

        Returns:
            bool: ``True`` if the chunk is active.
        """
        return key in self._loaded

    def __contains__(self, key: object) -> bool:
        """Supports ``key in chunk_tile``.

        Args:
            key: Candidate chunk key.

        Returns:
            bool: ``True`` if the key is in the loaded set.
        """
        return key in self._loaded

    def __len__(self) -> int:
        """Number of chunks currently loaded.

        Returns:
            int: Length of the loaded set.
        """
        return len(self._loaded)

    def load_chunk(self, key: ChunkKey) -> bool:
        """Loads a chunk into memory if not already present.

        Args:
            key: Target chunk key.

        Returns:
            bool: ``True`` if the chunk was just loaded, ``False`` if it
            was already active or not found in the config.
        """
        if key in self._loaded:
            self._loaded.move_to_end(key)
            return False

        config = self._tilemap.config
        if config is None:
            return False
        chunk = config.chunks.get(key)
        if chunk is None:
            return False

        self._tilemap._load_chunk(key, chunk)
        self._loaded[key] = None
        return True

    def unload_chunk(self, key: ChunkKey) -> bool:
        """Unloads a chunk from memory.

        Args:
            key: Target chunk key.

        Returns:
            bool: ``True`` if the chunk was previously active and has been
            unloaded, ``False`` otherwise.
        """
        if key not in self._loaded:
            return False
        self._tilemap._unload_chunk(key)
        del self._loaded[key]
        return True

    def unload_all(self) -> None:
        """Unloads every currently active chunk."""
        for key in list(self._loaded):
            self.unload_chunk(key)

    def update(self, visible_keys: set[ChunkKey]) -> None:
        """Syncs active chunks with the set of visible chunks.

        Loads chunks in the visible+margin area, unloads chunks outside
        the evict zone, and pins/evicts according to capacity. For small
        maps, every chunk is pinned at once.

        Args:
            visible_keys: Set of chunk keys currently visible in the viewport.
        """
        config = self._tilemap.config
        if config is None:
            return

        total_chunks = len(config.chunks)
        pin_all = total_chunks > 0 and total_chunks <= self._max_loaded

        if pin_all:
            # Small map: load every chunk in one go. Spreading loads
            # (max_loads_per_update) causes visible pop-in stutter while
            # panning before residency completes.
            for key in config.chunks:
                if key not in self._loaded:
                    self.load_chunk(key)
            return

        keep = self._keys_around(visible_keys, self._margin)
        evict_zone = self._keys_around(visible_keys, self._margin + 1)

        loads = 0
        for key in keep:
            if key not in config.chunks or key in self._loaded:
                continue
            if self._max_loads_per_update > 0 and loads >= self._max_loads_per_update:
                break
            self.load_chunk(key)
            loads += 1

        for key in list(self._loaded):
            if key not in evict_zone:
                self.unload_chunk(key)

        while len(self._loaded) > self._max_loaded:
            oldest, _ = self._loaded.popitem(last=False)
            self._tilemap._unload_chunk(oldest)

    def _keys_around(self, visible_keys: set[ChunkKey], margin: int) -> set[ChunkKey]:
        """Builds the set of chunk keys around visible_keys including the margin.

        Args:
            visible_keys: Central set of chunk keys.
            margin: Extra chunks added on each side (``<= 0`` = no-op).

        Returns:
            set[ChunkKey]: Union of the visible keys and their neighbors.
        """
        if margin <= 0:
            return set(visible_keys)
        result: set[ChunkKey] = set(visible_keys)
        for key in visible_keys:
            cx_s, cy_s = key.split(",", 1)
            try:
                cx = int(cx_s)
                cy = int(cy_s)
            except ValueError:
                continue
            for dx in range(-margin, margin + 1):
                for dy in range(-margin, margin + 1):
                    result.add(f"{cx + dx},{cy + dy}")
        return result

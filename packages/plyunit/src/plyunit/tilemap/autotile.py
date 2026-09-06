"""Neighbor-rule engine for the tilemap autotile system."""

import json
import random
from pathlib import Path
from typing import Any


class AutotileProcessor:
    """Offline/editor utility for computing autotile bitmasks.

    Reads the autotile configuration (an injected dict, or a JSON file
    path for backward-compat) and computes bitmasks from neighbors. Uses
    a per-map ``random.Random(seed)`` for deterministic results instead
    of the global ``random`` module.
    """

    NORTH = 1
    """Bitmask flag for the north direction."""
    EAST = 2
    """Bitmask flag for the east direction."""
    SOUTH = 4
    """Bitmask flag for the south direction."""
    WEST = 8
    """Bitmask flag for the west direction."""
    NORTH_EAST = 16
    """Bitmask flag for the northeast direction."""
    SOUTH_EAST = 32
    """Bitmask flag for the southeast direction."""
    SOUTH_WEST = 64
    """Bitmask flag for the southwest direction."""
    NORTH_WEST = 128
    """Bitmask flag for the northwest direction."""

    def __init__(
        self,
        config: dict | str | Path | None = None,
        *,
        seed: int | None = None,
    ) -> None:
        """Initializes AutotileProcessor.

        Args:
            config: Autotile configuration as a dict, OR a path to a JSON
                configuration file (backward-compat; blocking I/O — avoid at
                runtime). If ``None``, the processor starts empty (sets = {}).
            seed: Seed for the per-map RNG (deterministic). If ``None``, the
                RNG is unseeded (non-deterministic).
        """
        if isinstance(config, (str, Path)):
            with open(config, encoding="utf-8") as f:
                self.config = json.load(f)
        elif isinstance(config, dict):
            self.config = config
        else:
            self.config = {}
        self.sets = self.config.get("autotiles", {})
        self._rng = random.Random(seed)

    def calculate_bitmask(
        self, grid: list[list[str]], x: int, y: int, target_type: str, mode: str
    ) -> int:
        """Computes the bitmask for the cell at (x, y) based on the autotile mode.

        Args:
            grid: 2D array [y][x] containing tile types (strings).
            x: x position (column) of the cell being computed.
            y: y position (row) of the cell being computed.
            target_type: The target string type that counts as a valid neighbor.
            mode: Connection mode (e.g. "match_sides", "match_corners",
                "match_corners_and_sides").

        Returns:
            The integer bitmask value (a combination of direction flags).
        """
        rows = len(grid)
        cols = len(grid[0]) if rows > 0 else 0

        def is_match(cx, cy):
            """Returns True if the cell at (cx, cy) matches the target type."""
            if cy < 0 or cy >= rows or cx < 0 or cx >= cols:
                # Out of bounds connects to same type
                return True
            return grid[cy][cx] == target_type

        mask = 0

        n = is_match(x, y - 1)
        e = is_match(x + 1, y)
        s = is_match(x, y + 1)
        w = is_match(x - 1, y)

        if mode in ("match_sides", "match_corners_and_sides"):
            if n:
                mask |= self.NORTH
            if e:
                mask |= self.EAST
            if s:
                mask |= self.SOUTH
            if w:
                mask |= self.WEST

        if mode in ("match_corners", "match_corners_and_sides"):
            nw = is_match(x - 1, y - 1)
            ne = is_match(x + 1, y - 1)
            se = is_match(x + 1, y + 1)
            sw = is_match(x - 1, y + 1)

            if mode == "match_corners_and_sides":
                # For 8-way blob, corner is only active if both adjacent
                # sides are active
                if n and w and nw:
                    mask |= self.NORTH_WEST
                if n and e and ne:
                    mask |= self.NORTH_EAST
                if s and e and se:
                    mask |= self.SOUTH_EAST
                if s and w and sw:
                    mask |= self.SOUTH_WEST
            else:
                # pure corners
                if nw:
                    mask |= self.NORTH_WEST
                if ne:
                    mask |= self.NORTH_EAST
                if se:
                    mask |= self.SOUTH_EAST
                if sw:
                    mask |= self.SOUTH_WEST

        return mask

    def resolve_tile(
        self, set_id: str, bitmask: int, seed: int | None = None
    ) -> tuple[Any, float]:
        """Looks up tile data by bitmask for a given autotile set.

        Supports weighted random selection when the configuration defines
        variations.

        Args:
            set_id: Autotile set ID within the JSON configuration.
            bitmask: The computed integer bitmask value.
            seed: Optional seed to override the RNG per call. If ``None``,
                uses the per-map RNG (``self._rng``).

        Returns:
            A tuple containing:
            - The region data (e.g. a list [x, y, w, h] or an asset ID).
            - The weight (float) of the chosen region.
        """
        if set_id not in self.sets:
            return (None, 1.0)

        tile_set = self.sets[set_id]
        bitmasks_map = tile_set.get("bitmasks", {})
        fallback = tile_set.get("fallback_region")

        val = bitmasks_map.get(str(bitmask))
        if val is None:
            return (fallback, 1.0)

        if isinstance(val, dict) and "random" in val:
            choices = val["random"]
            total = sum(c.get("weight", 1.0) for c in choices)

            if seed is not None:
                rnd = random.Random(seed)
                r = rnd.uniform(0, total)
            else:
                r = self._rng.uniform(0, total)

            upto = 0.0
            for c in choices:
                weight = c.get("weight", 1.0)
                upto += weight
                if r <= upto:
                    return (c.get("id") or c.get("rect"), weight)
            last_choice = choices[-1]
            return (
                last_choice.get("id") or last_choice.get("rect"),
                last_choice.get("weight", 1.0),
            )

        return (val, 1.0)

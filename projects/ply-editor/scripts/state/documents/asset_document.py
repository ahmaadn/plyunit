from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from plyunit.assets.types import (
    ImageConfig,
    SpriteSheetConfig,
    TextureData,
    TextureProperty,
)
from scripts.services.json_io import write_json_atomic
from scripts.state.document import Document, DocumentKind

if TYPE_CHECKING:
    from scripts.services.assets import Assets


@dataclass(slots=True, frozen=True)
class GridParams:
    """Grid parameters for assisting region selection on spritesheets.

    The grid is a **visual aid only**: it never creates regions
    automatically. The user selects a cell, then a region is created
    from that cell.

    Attributes:
        cell_width: Width of one cell in pixels.
        cell_height: Height of one cell in pixels.
        offset_x: Horizontal grid origin offset.
        offset_y: Vertical grid origin offset.
        spacing_x: Horizontal gap between cells.
        spacing_y: Vertical gap between cells.
        margin_x: Left/right image margin skipped by the grid.
        margin_y: Top/bottom image margin skipped by the grid.
        snap: When True, region resizing snaps to grid multiples;
            when False, free per-pixel.
    """

    cell_width: int = 16
    cell_height: int = 16
    offset_x: int = 0
    offset_y: int = 0
    spacing_x: int = 0
    spacing_y: int = 0
    margin_x: int = 0
    margin_y: int = 0
    snap: bool = True

    @property
    def step_x(self) -> int:
        """Horizontal distance between consecutive cell origins."""
        return max(1, self.cell_width + self.spacing_x)

    @property
    def step_y(self) -> int:
        """Vertical distance between consecutive cell origins."""
        return max(1, self.cell_height + self.spacing_y)

    def cell_at(self, x: float, y: float) -> tuple[int, int] | None:
        """Grid cell containing the image point ``(x, y)``.

        Args:
            x: X coordinate in image pixel space.
            y: Y coordinate in image pixel space.

        Returns:
            ``(col, row)``, or ``None`` when the point falls in a margin
            or the spacing gap between cells.
        """
        local_x = x - self.margin_x - self.offset_x
        local_y = y - self.margin_y - self.offset_y
        if local_x < 0 or local_y < 0:
            return None

        col = int(local_x // self.step_x)
        row = int(local_y // self.step_y)
        # Titik di dalam spacing bukan bagian dari petak mana pun.
        if local_x - col * self.step_x >= self.cell_width:
            return None
        if local_y - row * self.step_y >= self.cell_height:
            return None
        return col, row

    def cell_rect(self, col: int, row: int) -> tuple[float, float, float, float]:
        """Pixel rect of a single grid cell."""
        return (
            float(self.margin_x + self.offset_x + col * self.step_x),
            float(self.margin_y + self.offset_y + row * self.step_y),
            float(self.cell_width),
            float(self.cell_height),
        )

    def snap_value(self, value: float, *, axis: str) -> float:
        """Round a coordinate to the nearest grid line.

        Args:
            value: The pixel value to round.
            axis: ``"x"`` or ``"y"``.

        Returns:
            The snapped value; the original value when :attr:`snap` is
            off.
        """
        if not self.snap:
            return value
        if axis == "x":
            origin, step = self.margin_x + self.offset_x, self.step_x
        else:
            origin, step = self.margin_y + self.offset_y, self.step_y
        return origin + round((value - origin) / step) * step

    def to_dict(self) -> dict[str, Any]:
        """Serialize the grid parameters to a plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> GridParams:
        """Parse grid parameters, tolerating missing or mistyped fields.

        Also accepts field names from the old slicer (``frame_width`` /
        ``frame_height``) so existing sidecars remain readable.
        """
        if not isinstance(data, dict):
            return cls()

        values: dict[str, Any] = {}
        aliases = {
            "cell_width": ("cell_width", "frame_width"),
            "cell_height": ("cell_height", "frame_height"),
            "offset_x": ("offset_x",),
            "offset_y": ("offset_y",),
            "spacing_x": ("spacing_x",),
            "spacing_y": ("spacing_y",),
            "margin_x": ("margin_x",),
            "margin_y": ("margin_y",),
        }
        for field_name, keys in aliases.items():
            for key in keys:
                if key in data:
                    try:
                        values[field_name] = max(0, int(data[key]))
                    except (TypeError, ValueError):
                        pass
                    break

        # Defaults are read from an instance, not the class: on a slots
        # dataclass, class attributes are descriptors, not default values.
        defaults = cls()
        values["cell_width"] = max(1, values.get("cell_width", defaults.cell_width))
        values["cell_height"] = max(1, values.get("cell_height", defaults.cell_height))
        if "snap" in data:
            values["snap"] = bool(data["snap"])
        return cls(**values)


@dataclass(slots=True, kw_only=True)
class ImageDocument(Document):
    """An open image or spritesheet, including its regions and grid.

    Attributes:
        asset_id: Identifier in the asset index.
        image_path: Path of the source image.
        texture_property: Texture import settings written to the sidecar.
        asset_type: ``"image"`` or ``"spritesheet"``.
        confg_path: Sidecar JSON path, or ``None`` until first save.
        grid: Selection grid. Visual only; it does not create regions.
    """

    asset_id: str
    image_path: Path
    texture_property: TextureProperty
    asset_type: Literal["image", "spritesheet"] = field(default="image")
    confg_path: Path | None = None

    grid: GridParams = field(default_factory=GridParams)
    _regions: list[TextureData] = field(default_factory=list)
    # pyrefly: ignore [bad-assignment]
    _texture_data: TextureData = field(default=None, init=False)

    @classmethod
    def from_asset_id(cls, asset_id: str, assets: Assets) -> ImageDocument:
        """Build a document from an asset already loaded in the index.

        Args:
            asset_id: Identifier of the loaded asset.
            assets: Asset index that owns the config and textures.

        Returns:
            A document whose regions and texture come from ``assets``.

        Raises:
            RuntimeError: When ``asset_id`` is not in the index.
        """
        config = assets.get_config_for(asset_id)
        if config is None:
            raise RuntimeError(f"asset_id {asset_id!r} not found")

        doc = cls(
            kind=DocumentKind.IMAGE,
            asset_id=asset_id,
            image_path=config.image_path,
            confg_path=config.config_path,
            asset_type=config.type,
            texture_property=config.texture,
        )

        doc._regions = assets.get_regions(asset_id)
        doc._texture_data = assets.get_texture_data(asset_id)

        return doc

    @property
    def is_spritesheet(self) -> bool:
        """True when this document stores named regions."""
        return self.asset_type == "spritesheet"

    @property
    def is_created(self) -> bool:
        """True when a sidecar JSON path already exists."""
        return bool(self.confg_path)

    @property
    def path(self) -> Path:
        """Source image path used as the tab identity."""
        return self.image_path

    @property
    def title(self) -> str:
        """File name shown on the tab."""
        return self.path.name

    def save(self, path: Path | None = None) -> Path:
        """Write the image or spritesheet sidecar next to the image.

        When no sidecar exists yet, a unique ``<stem>.json`` name is
        chosen beside the image. An existing sidecar is overwritten.

        Args:
            path: Unused. The destination is derived from the image path
                or the existing sidecar.

        Returns:
            Absolute path of the sidecar that was written.
        """
        if not self.is_created:
            base_name = self.image_path.stem
            path = self.image_path.with_name(f"{base_name}.json")

            i = 1
            while path.exists():
                path = self.image_path.with_name(f"{base_name}({i}).json")
                i += 1

            self.confg_path = path.absolute()

        data = ImageConfig(
            id=self.asset_id,
            type="image",
            image_path=str(self.image_path),
            config_path=str(self.confg_path),
            texture=self.texture_property.to_dict(),
        )

        if self.asset_type == "spritesheet":
            data = SpriteSheetConfig(
                id=self.asset_id,
                image_path=str(self.image_path),
                config_path=str(self.confg_path),
                texture=self.texture_property.to_dict(),
                type="spritesheet",
                regions={region.id: region.source_rect for region in self.regions},
            )

        # pyrefly: ignore [bad-argument-type]
        write_json_atomic(self.confg_path, data=data)

        # pyrefly: ignore [bad-return]
        return self.confg_path

    @property
    def regions(self) -> list[TextureData]:
        """Named texture regions belonging to this asset."""
        return self._regions

    def region_at(self, x: float, y: float) -> int:
        """Index of the region containing the image point, or ``-1``.

        Regions added later are checked first so the one that appears
        on top is the one selected.
        """
        for i in range(len(self.regions) - 1, -1, -1):
            rx, ry, rw, rh = self.regions[i].source_rect
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return i
        return -1

    def set_asset_type(self, asset_type: str) -> bool:
        """Toggle between plain image and spritesheet.

        Switching to ``image`` **does not discard** the region list:
        it is stashed and restored if the user switches back to
        ``spritesheet``.

        Args:
            asset_type: ``"image"`` or ``"spritesheet"``.

        Returns:
            True when the type actually changed.
        """
        if asset_type not in ("image", "spritesheet") or asset_type == self.asset_type:
            return False

        self.asset_type = asset_type
        self.mark_dirty()
        return True

    def set_grid(self, grid: GridParams) -> bool:
        """Replace grid parameters.

        The grid is only a selection aid, so changing it **does not**
        touch any existing regions.
        """
        if grid == self.grid:
            return False
        self.grid = grid
        self.mark_dirty()
        return True

    def update_grid(self, **changes: Any) -> bool:
        """Change a subset of grid fields."""
        return self.set_grid(replace(self.grid, **changes))

    def add_region_at_cell(self, col: int, row: int) -> int:
        """Create a region exactly the size of one grid cell.

        Args:
            col: Cell column.
            row: Cell row.

        Returns:
            Index of the new region, or the index of the region already
            occupying that cell.
        """
        rect = self.grid.cell_rect(col, row)
        for i, region in enumerate(self.regions):
            if region.source_rect == rect:
                return i

        name = self.unique_region_name(f"{self.image_path.stem}_{col}_{row}")
        self.regions.append(
            TextureData(
                id=name,
                parent_id=self.asset_id,
                texture=self._texture_data.texture,
                source_rect=rect,
            )
        )
        if not self.is_spritesheet:
            self.asset_type = "spritesheet"
        self.mark_dirty()
        return len(self.regions) - 1

    def unique_region_name(self, base: str) -> str:
        """Generate a unique region name based on ``base``."""
        existing = {r.id for r in self.regions}
        if base not in existing:
            return base
        index = 2
        while f"{base}_{index}" in existing:
            index += 1
        return f"{base}_{index}"

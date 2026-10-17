from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Final

import pyray as pr

import plyunit
from plyunit.utils import contains
from scripts import constants as const
from scripts.app import events
from scripts.state.document import DocumentKind
from scripts.state.documents.asset_document import ImageDocument
from scripts.state.ui import StatusType

if TYPE_CHECKING:
    from app import EditorApp

    from plyunit.assets.types import TextureData
    from plyunit.core.types import ColorType, RectType, SizeType
    from plyunit.services.input._types import CursorShape

logger = logging.getLogger(__name__)


CURSOR_DEFAULT: Final[CursorShape] = "arrow"
CURSOR_BY_EDGE: Final[dict[str, CursorShape]] = {
    "tl": "resize_nwse",
    "br": "resize_nwse",
    "tr": "resize_nesw",
    "bl": "resize_nesw",
    "l": "resize_ew",
    "r": "resize_ew",
    "t": "resize_ns",
    "b": "resize_ns",
}
MIN_REGION_SIZE: Final[int] = 4


def _color(rgba: ColorType) -> pr.Color:
    """Build a raylib color from an RGBA tuple.

    Args:
        rgba: Red, green, blue, and alpha channels, each ``0``..``255``.

    Returns:
        The matching raylib color.
    """
    return pr.Color(rgba[0], rgba[1], rgba[2], rgba[3])


def _truncate_text(text: str, max_width: float, font_size: int) -> str:
    """Truncate ``text`` so it fits within ``max_width`` pixels.

    When text is truncated, an ``...`` suffix is appended. Returns an
    empty string when even ``...`` does not fit (box too narrow).
    """
    if not text or max_width <= 0.0:
        return ""
    if pr.measure_text(text, font_size) <= max_width:
        return text
    trimmed = text
    while trimmed and pr.measure_text(f"{trimmed}...", font_size) > max_width:
        trimmed = trimmed[:-1]
    return f"{trimmed}..." if trimmed else ""


class RegionOverlay(plyunit.ServiceUnit):
    def __init__(self) -> None:
        super().__init__("RegionOverlay", tags={"service", "region_overlay"})

        self._is_holding_region: bool = False  # True saat move
        self._edge_selected: str | None = None  # terisi saat resize
        self._cursor_active: bool = False  # True jika kita yang mengubah cursor

        # Snapshot saat mulai resize / move
        self._start_rect: tuple[float, float, float, float] | None = None
        self._start_mouse: tuple[float, float] = (0.0, 0.0)

        self._handle_size: float = 2
        self.enabled: bool = True

    def on_attach(self, app: EditorApp) -> None:
        """Bind shared services."""
        self.ctx = app.ctx
        self.camera = app.camera
        self.bus = app.bus

        self.input = app.input
        self.mouse = app.mouse

    @property
    def document(self) -> ImageDocument:
        """The active workspace document, expected to be an image."""
        # pyrefly: ignore [bad-return]
        return self.ctx.workspace.active

    def update(self, dt: float) -> None:
        regions = self.document.regions
        index = self.document.selected_region

        hover_edge: str | None = None
        is_over_region = False
        mouse_pos = (0.0, 0.0)
        valid = 0 <= index < len(regions)

        if valid:
            region = regions[index].source_rect
            mouse_pos = self.camera.screen_to_world(*self.mouse.position)
            hover_edge = self._check_resize_handle(region, *mouse_pos)
            is_over_region = hover_edge is not None or contains(mouse_pos, region)

            if not self.enabled and self._start_rect is None:
                hover_edge = None
                is_over_region = False

        elif self._start_rect is not None:
            # Region hilang di tengah drag (mis. dihapus): batalkan interaksi.
            self._is_holding_region = False
            self._edge_selected = None
            self._start_rect = None

        # Start / stop interaksi
        if self.mouse.is_pressed("left") and is_over_region:
            x, y, w, h = region
            self._start_mouse = mouse_pos
            self._start_rect = (min(x, x + w), min(y, y + h), abs(w), abs(h))
            if hover_edge:
                self._edge_selected = hover_edge  # resize
            else:
                self._is_holding_region = True  # move
        elif not self.mouse.is_down("left"):
            self._is_holding_region = False
            self._edge_selected = None
            self._start_rect = None

        if valid and self._start_rect and self.mouse.is_down("left"):
            dx = mouse_pos[0] - self._start_mouse[0]
            dy = mouse_pos[1] - self._start_mouse[1]

            if self._edge_selected:
                regions[index].source_rect = self._compute_resized_rect(
                    self._start_rect, self._edge_selected, dx, dy
                )
            elif self._is_holding_region:
                sx, sy, sw, sh = self._start_rect
                regions[index].source_rect = (
                    round(sx + dx),
                    round(sy + dy),
                    round(sw),
                    round(sh),
                )

        active_edge = self._edge_selected or (
            None if self._is_holding_region else hover_edge
        )

        if active_edge:
            self.mouse.set_cursor(CURSOR_BY_EDGE[active_edge])
            self._cursor_active = True
        elif self._cursor_active:
            self.mouse.set_cursor(CURSOR_DEFAULT)
            self._cursor_active = False

    @staticmethod
    def _compute_resized_rect(
        start_rect: tuple[float, float, float, float],
        edge: str,
        dx: float,
        dy: float,
    ) -> tuple[int, int, int, int]:
        """Return the rect resized from `start_rect` by dragging `edge` by (dx, dy).

        The result never flips or shrinks below MIN_REGION_SIZE.
        """
        sx, sy, sw, sh = start_rect
        left, top, right, bottom = sx, sy, sx + sw, sy + sh

        if "l" in edge:
            left = min(left + dx, right - MIN_REGION_SIZE)
        if "r" in edge:
            right = max(right + dx, left + MIN_REGION_SIZE)
        if "t" in edge:
            top = min(top + dy, bottom - MIN_REGION_SIZE)
        if "b" in edge:
            bottom = max(bottom + dy, top + MIN_REGION_SIZE)

        return round(left), round(top), round(right - left), round(bottom - top)

    def _check_resize_handle(
        self, region: RectType, mx: float, my: float
    ) -> str | None:
        """Return the edge/corner under (mx, my): tl/tr/bl/br/t/b/l/r, or None."""
        x, y, w, h = region
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h

        left, top, right, bottom = x, y, x + w, y + h
        m = self._handle_size

        if not (left - m <= mx <= right + m and top - m <= my <= bottom + m):
            return None

        vertical = "t" if abs(my - top) <= m else "b" if abs(my - bottom) <= m else ""
        horizontal = "l" if abs(mx - left) <= m else "r" if abs(mx - right) <= m else ""
        return (vertical + horizontal) or None

    @property
    def is_interacting(self) -> bool:
        """True while a resize or move drag is in progress."""
        return self._edge_selected is not None or self._is_holding_region


class ImageCanvas(plyunit.ServiceUnit):
    """Interactive viewport for image and spritesheet assets.

    Handles zoom, pan, region picking, and rendering of the image with
    its grid and region overlays.
    """

    def __init__(self) -> None:
        """Create the canvas with no selection and no active pan."""
        super().__init__("ImageCanvas", tags={"service", "image_canvas", "canvas"})

        self.imgui_wants_mouse: bool = False
        self.imgui_wants_keyboard: bool = False

        self._panning = False
        self._event_active = False

        self.region_overlay = RegionOverlay()

    def on_attach(self, app: EditorApp) -> None:
        """Bind shared services and subscribe to asset-open requests.

        Args:
            app: The running editor application.
        """
        self.ctx = app.ctx
        self.camera = app.camera
        self.bus = app.bus
        self.assets = app.assets

        self.input = app.input
        self.mouse = app.mouse

        app.bus.subscribe(events.ASSET_OPEN_REQUESTED, self.on_open_asset_request)

    def set_active(self):
        self._event_active = True
        logger.info("Image Canvas Event Active")
        bus = self.one("@EventBus")

        bus.subscribe(events.ASSET_GRID_CHANGE_REQUESTED, self.on_grid_change_request)
        bus.subscribe(events.ASSET_FIT_REQUESTED, self.fit_asset)
        bus.subscribe(events.REGION_SELECTED, self.on_region_selected)

    def disable(self):
        self._event_active = False
        logger.info("Image Canvas Event Disable")
        bus = self.one("@EventBus")
        bus.unsubscribe(events.ASSET_GRID_CHANGE_REQUESTED, self.on_grid_change_request)
        bus.unsubscribe(events.ASSET_FIT_REQUESTED, self.fit_asset)
        bus.unsubscribe(events.REGION_SELECTED, self.on_region_selected)

    def update(self, dt: float) -> None:
        """Handle zoom, pan, and region picking for the active image.

        Args:
            dt: Frame delta time in seconds. Unused; input is polled.
        """
        if not self.ctx.workspace.active:
            return

        self._handle_zoom()
        self._handle_pan()

        overlay = self.region_overlay
        overlay.enabled = not (
            self.imgui_wants_mouse or self._panning or self.input.is_down("space")
        )
        overlay.update(dt)

        if not overlay.is_interacting:
            self._handle_pick()

    def reset(self) -> None:
        """Clear the selected region and stop an in-progress pan."""
        self._panning = False

    @property
    def document(self) -> ImageDocument:
        """The active workspace document, expected to be an image."""
        # pyrefly: ignore [bad-return]
        return self.ctx.workspace.active

    def image_size(self) -> SizeType | None:
        """Size of the active image asset in pixels."""
        if self.document is None:
            return None

        try:
            texture_data = self.assets.get_texture_data(self.document.asset_id)
            (_x, _y, width, height) = texture_data.source_rect
            if width <= 0 or height <= 0:
                return None
            return float(width), float(height)
        except KeyError:
            return None

    def _handle_zoom(self) -> None:
        """Zoom from the mouse wheel unless ImGui already owns the mouse."""
        if self.imgui_wants_mouse:
            return
        wheel = self.mouse.get_wheel_move()
        if wheel:
            self.camera.zoom_by(wheel * const.ZOOM_STEP)

    def _handle_pan(self) -> None:
        """Pan with the middle button, or left button while Space is held."""

        middle = self.mouse.is_down("middle")
        space = self.input.is_down("space")
        left = self.mouse.is_down("left")

        if self._panning:
            if not (middle or left):
                self._panning = False
                return
            mx, my = self.mouse.movement
            zoom = self.camera.effective_zoom()
            if zoom > 0:
                self.camera.pan_by(-mx / zoom, -my / zoom)
            return

        if (middle or (left and space)) and not self.imgui_wants_mouse:
            self._panning = True

    def _handle_pick(self) -> None:
        """Handle left-click: select region or create one from a grid cell."""
        if self.imgui_wants_mouse or self._panning:
            return

        if not self.mouse.is_pressed("left"):
            return

        if self.input.is_down("space"):
            return

        document = self.document
        if document is None:
            return

        x, y = self.camera.screen_to_world(*self.mouse.position)

        size = self.image_size()
        if size is None or not (0 <= x < size[0] and 0 <= y < size[1]):
            return

        index = document.region_at(x, y)
        if index < 0 and document.is_spritesheet:
            cell = document.grid.cell_at(x, y)
            if cell is not None:
                index = document.add_region_at_cell(*cell)

        if index < 0:
            self.document.selected_region = -1
            return

        self.document.selected_region = index
        # self.bus.publish(
        #     events.REGION_PICKED, index, document.regions[index].source_rect
        # )

    def render_submit(self, renderer: plyunit.Renderer) -> None:
        """Submit the image asset and its overlay for rendering."""
        document = self.document
        if document is None:
            return

        try:
            texture_data = self.assets.get_texture_data(document.asset_id)

            (sx, sy, sw, sh) = texture_data.source_rect

            renderer.render_sprite(
                texture=texture_data.texture,
                z=0,
                layer=plyunit.Layer.WORLD,
                source=(float(sx), float(sy), float(sw), float(sh)),
                dest=(0.0, 0.0, float(sw), float(sh)),
                tint=(255, 255, 255, 255),
                screen_space=False,
            )
            renderer.render_custom(
                draw_func=self._draw_overlay,
                z=9500,
                layer=plyunit.Layer.UI_WORLD,
                screen_space=False,
            )
        except KeyError:
            ...

    def _draw_overlay(self, canvas: plyunit.interfaces.ICanvas2D) -> None:
        """Draw the guide grid and region boxes on top of the image."""
        _ = canvas
        document = self.document
        size = self.image_size()
        if document is None or size is None:
            return

        pr.rl_set_texture(0)
        width, height = size
        zoom = max(0.001, self.camera.effective_zoom())
        thickness = max(0.02, 1.0 / zoom)

        if document.is_spritesheet:
            self._draw_grid(document, width, height, thickness)

        self._draw_regions(document, thickness)

        # Bingkai gambar digambar terakhir agar selalu terlihat.
        pr.draw_rectangle_lines_ex(
            pr.Rectangle(0.0, 0.0, width, height),
            thickness,
            _color(const.COLOR_ACCENT),
        )

    def _draw_grid(self, doc: ImageDocument, width: float, height: float, thickness):
        """Draw the spritesheet guide grid inside the image bounds.

        Vertical and horizontal lines are spaced by the grid step and
        shifted by the grid's effective offset, so the lines align with
        the cell boundaries. Lines outside the margins are skipped.

        Args:
            document: The image document whose grid settings are used.
            width: The image width in pixels.
            height: The image height in pixels.
            thickness: Line thickness in pixels (already zoom-compensated).
        """
        grid = doc.grid
        color = _color(const.COLOR_GRID)

        start_x = grid.margin_x
        end_x = width - grid.margin_x
        start_y = grid.margin_y
        end_y = height - grid.margin_y

        curr_x = start_x + grid.eff_offset_x - grid.step_x
        while curr_x <= end_x:
            left_x = curr_x
            right_x = curr_x + grid.cell_height

            if left_x >= start_x and left_x <= end_x:
                pr.draw_line_ex(
                    pr.Vector2(left_x, start_y),
                    pr.Vector2(left_x, end_y),
                    thickness,
                    color,
                )

            # Garis kanan sel (hanya digambar terpisah jika ada spacing)
            if grid.spacing_x > 0 and right_x >= start_x and right_x <= end_x:
                pr.draw_line_ex(
                    pr.Vector2(right_x, start_y),
                    pr.Vector2(right_x, end_y),
                    thickness,
                    color,
                )

            curr_x += grid.step_x

        curr_y = start_y + grid.eff_offset_y - grid.step_y
        while curr_y <= end_y:
            top_y = curr_y
            bottom_y = curr_y + grid.cell_height

            if top_y >= start_y and top_y <= end_y:
                pr.draw_line_ex(
                    pr.Vector2(start_x, top_y),
                    pr.Vector2(end_x, top_y),
                    thickness,
                    color,
                )

            if grid.spacing_y > 0 and bottom_y >= start_y and bottom_y <= end_y:
                pr.draw_line_ex(
                    pr.Vector2(start_x, bottom_y),
                    pr.Vector2(end_x, bottom_y),
                    thickness,
                    color,
                )
            curr_y += grid.step_y

    def _draw_regions(self, document: ImageDocument, thickness: float) -> None:
        """Draw the bounding box of each region; the selected one is
        highlighted."""
        for i, region in enumerate(document.regions):
            self._draw_region(i, region, thickness)

    def _draw_region(
        self,
        index: int,
        region: TextureData,
        thickness: float,
    ) -> None:
        """Draw one region's bounding box and its name label."""
        x, y, w, h = region.source_rect
        selected = index == self.document.selected_region
        color = _color(const.COLOR_SELECTION if selected else const.COLOR_REGION)

        pr.draw_rectangle_lines_ex(
            pr.Rectangle(x, y, w, h),
            thickness * (2.0 if selected else 1.0),
            color,
        )
        self._draw_region_name(region.id, x, y, w)

    def _draw_region_name(
        self,
        name: str,
        x: float,
        y: float,
        width: float,
    ) -> None:
        """Region name at the top-left corner of its box.

        Names are truncated with ``...`` when wider than the region box;
        a semi-transparent background keeps the text readable over the
        image.
        """
        label = _truncate_text(
            name, width - const.REGION_NAME_PADDING * 2.0, const.REGION_NAME_FONT_SIZE
        )
        if not label:
            return
        label_w = float(pr.measure_text(label, const.REGION_NAME_FONT_SIZE))
        pr.draw_rectangle(
            int(x + const.REGION_NAME_PADDING - 1.0),
            int(y + const.REGION_NAME_PADDING - 1.0),
            int(label_w + 2.0),
            int(const.REGION_NAME_FONT_SIZE + 2.0),
            _color(const.COLOR_REGION_NAME_BG),
        )
        pr.draw_text(
            label,
            int(x + const.REGION_NAME_PADDING),
            int(y + const.REGION_NAME_PADDING),
            const.REGION_NAME_FONT_SIZE,
            _color(const.COLOR_REGION_NAME),
        )

    def on_open_asset_request(self, asset_id: str) -> bool:
        """Open an image asset in a tab, or focus it if already open.

        Args:
            asset_id: Identifier of the scanned asset.

        Returns:
            ``True`` when a tab is focused or created; ``False`` when the
            asset id is unknown.
        """
        logger.info(f"Asset request to open :{asset_id}")

        assets = self.one("@Assets")
        asset_data = assets.get_config_for(asset_id)

        if asset_data is None:
            self.ctx.ui.set_status(f"Asset not found : {asset_id}", StatusType.ERROR)
            return False

        main_content = self.one("@MainContent")

        # A sidecar may not exist yet, so tab matching uses the asset id.
        for index, doc in enumerate(self.ctx.workspace.tabs):
            if doc.kind is not DocumentKind.IMAGE:
                continue

            if isinstance(doc, ImageDocument) and doc.asset_id == asset_id:
                main_content.activate_tab(index)
                self.ctx.workspace.select_tab_externally(index)
                return True

        doc = ImageDocument.from_asset_id(asset_id, assets)
        main_content.store_active_camera()
        self.ctx.workspace.add(doc)
        main_content._bind_active_tab()
        self.ctx.workspace.select_tab_externally(self.ctx.workspace.active_index)
        self.fit_asset()
        self.reset()
        self.ctx.ui.set_status(
            f"Asset Opened : {doc.title}, tabs: {self.ctx.workspace.active_index}"
        )
        if not self._event_active:
            self.set_active()
        return True

    def on_grid_change_request(self, data: dict):
        grid = replace(self.document.grid, **data)
        self.document.set_grid(grid)

    def fit_asset(self) -> None:
        """Adjust zoom so the entire image asset is visible."""
        doc = self.document
        if doc is None:
            return

        (_x, _y, width, height) = doc._texture_data.source_rect
        rect = (0.0, 0.0, float(width), float(height))
        shell = self.one("@EditorShell")
        viewport = shell.editor_screen.layout.viewport
        self.one("@Camera2D").fit_to_rect(rect, (viewport.width, viewport.height))

    def on_region_selected(self, index: int):
        self.document.selected_region = index


class MainContent(plyunit.ServiceUnit):
    """Coordinates the active document view and tab switching.

    Owns the :class:`ImageCanvas` and routes update/render calls to the
    correct canvas based on the active document kind.
    """

    def __init__(self) -> None:
        """Create the service and its image canvas."""
        super().__init__("MainContent", tags={"service", "main_content"})

        self.image_canvas = ImageCanvas()

    def on_attach(self, app: EditorApp) -> None:
        """Bind the app context and subscribe to tab-bar actions.

        Args:
            app: The running editor application.
        """
        self.ctx = app.ctx

        app.bus.subscribe(events.TAB_ACTION_REQUEST, self.on_handle_tab_actions)

    def update(
        self,
        dt: float,
        *,
        imgui_wants_mouse: bool = False,
        imgui_wants_keyboard: bool = False,
    ) -> None:
        """Forward input and the frame tick to the active canvas.

        Args:
            dt: Frame delta time in seconds.
            imgui_wants_mouse: When ``True``, the canvas ignores the mouse.
            imgui_wants_keyboard: When ``True``, the canvas ignores the
                keyboard.
        """
        doc = self.ctx.workspace.active
        if not doc or doc is None:
            return

        if doc.kind == DocumentKind.IMAGE:
            self.image_canvas.imgui_wants_mouse = imgui_wants_mouse
            self.image_canvas.imgui_wants_keyboard = imgui_wants_keyboard
            self.image_canvas.update(dt)

    def render_submit(self, renderer: plyunit.Renderer) -> None:
        """Submit the active document's canvas to the renderer.

        Args:
            renderer: Frame renderer that collects draw commands.
        """
        doc = self.ctx.workspace.active
        if not doc or doc is None:
            return

        if doc is not None and doc.kind == DocumentKind.IMAGE:
            self.image_canvas.render_submit(renderer)

    def activate_tab(self, index: int) -> None:
        """Switch to another tab."""
        if index == self.ctx.workspace.active_index:
            return

        is_prev_kind = (
            self.ctx.workspace.active.kind if self.ctx.workspace.active else None
        )

        self.store_active_camera()
        if self.ctx.workspace.activate(index):
            self._bind_active_tab()

        if not self.ctx.workspace.active:
            return

        # Load and unload event
        is_active_kind = self.ctx.workspace.active.kind
        if is_prev_kind == is_active_kind:
            logger.debug("Event not set because prev and active same doc")
            return

        if is_prev_kind == DocumentKind.IMAGE:
            self.image_canvas.disable()

        if is_active_kind == DocumentKind.IMAGE:
            self.image_canvas.set_active()

    def close_tab(self, index: int, *, force: bool = False) -> bool:
        """Close one tab, deferring dirty tabs unless forced.

        Args:
            index: Tab index to close.
            force: When ``True``, close even if the document is dirty.

        Returns:
            ``True`` when the tab was closed. ``False`` when the index is
            invalid or a dirty tab still needs confirmation.
        """
        if not (0 <= index < len(self.ctx.workspace.tabs)):
            return False

        tab = self.ctx.workspace.tabs[index]
        if tab.dirty and not force:
            self._close_prompt_index = index
            return False

        self.ctx.workspace.close(index)
        self._close_prompt_index = None
        if not self.ctx.workspace.is_empty:
            self._bind_active_tab()

        return True

    def _bind_active_tab(self) -> None:
        """Point all subsystems at the currently active tab.

        Documents, history, cameras, canvas, and panels all hold direct
        references. Switching tabs swaps those references together
        rather than rebuilding the UI.

        Since tabs may contain non-map documents, map-specific
        subsystems are only redirected when the active tab contains a
        map.
        """
        doc = self.ctx.workspace.active
        if doc is None:
            return

        camera = self.one("@Camera2D")
        camera.center_on(doc.camera.x, doc.camera.y)
        camera.set_zoom(doc.camera.zoom)

        if isinstance(doc, ImageDocument):
            self.image_canvas.reset()

    def on_handle_tab_actions(self, actions: list) -> None:
        """Apply actions from the tab bar after the ImGui frame is drawn."""
        from scripts.ui.panels.tabs import TabActionKind

        for action in actions:
            if action.kind is TabActionKind.ACTIVATE:
                self.activate_tab(action.index)
            elif action.kind is TabActionKind.CLOSE:
                self.close_tab(action.index)
            elif action.kind is TabActionKind.CLOSE_OTHERS:
                # self._close_others(action.index)
                ...
            elif action.kind is TabActionKind.CLOSE_ALL:
                # self._close_all()
                ...

            elif action.kind is TabActionKind.SAVE:
                # self.activate_tab(action.index)
                # self.action_save_active()
                ...
            elif action.kind is TabActionKind.NEW_MAP:
                # self.action_new_map()
                ...

    def store_active_camera(self) -> None:
        """Copy the live camera into the active document."""
        doc = self.ctx.workspace.active
        if doc is None:
            return

        camera = self.one("@Camera2D")
        doc.camera.x = float(camera.pos[0])
        doc.camera.y = float(camera.pos[1])
        doc.camera.zoom = float(camera.zoom)

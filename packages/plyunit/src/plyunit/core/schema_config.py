"""Schema configuration dataclasses for ``App`` setup.

Defines ``AppConfig`` plus its nested ``PhysicsConfig``, ``ImGuiConfig``, and
``AudioConfig`` sections, with field validation and JSON/dict loading support.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Self

from plyunit.core.types import ColorType
from plyunit.utils.io import read_json

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PhysicsConfig:
    """Optional configuration for the physics service.

    Active only if ``enabled`` is ``True``. When enabled, ``init`` builds
    ``Physics`` via :func:`build_physics_service` and adds it to ``App``
    (stepped automatically each substep via the ``on_fixed_update`` signal).
    """

    enabled: bool = False
    """Whether the physics service is enabled."""

    gravity: tuple[float, float] = (0.0, 900.0)
    """Gravity components ``(gx, gy)`` in pixels/second^2."""

    world_bounds: tuple[float, float, float, float] = (
        -10000.0,
        -10000.0,
        10000.0,
        10000.0,
    )
    """World bounds ``(min_x, min_y, max_x, max_y)`` for clamping positions."""

    spatial_hash_dim: float = 100.0
    """Spatial hash cell size (pixels)."""

    spatial_hash_count: int = 1000
    """Initial number of cells allocated for the spatial hash."""

    sleep_time_threshold: float = 0.5
    """Time threshold (seconds) before a body is considered asleep."""

    idle_speed_threshold: float = 10.0
    """Speed threshold below which a body is considered asleep."""

    iterations: int = 10
    """Number of solver iterations per fixed step."""

    damping: float = 1.0
    """Velocity damping factor (``1.0`` = no damping)."""

    enable_spatial_hash: bool = True
    """Enable the spatial hash for broadphase queries."""

    def validate(self) -> None:
        """Validates the physics fields and raises ``ValueError`` if invalid."""
        if len(self.gravity) != 2:
            raise ValueError("physics.gravity must be a (gx, gy) tuple")
        if len(self.world_bounds) != 4:
            raise ValueError("physics.world_bounds must be a 4-tuple")
        if self.spatial_hash_dim <= 0:
            raise ValueError("physics.spatial_hash_dim must be > 0")
        if self.spatial_hash_count <= 0:
            raise ValueError("physics.spatial_hash_count must be > 0")
        if self.iterations <= 0:
            raise ValueError("physics.iterations must be > 0")
        if self.damping < 0:
            raise ValueError("physics.damping must be >= 0")


@dataclass(slots=True)
class ImGuiConfig:
    """Optional configuration for the ImGui service (immediate-mode UI).

    Active only if ``enabled`` is ``True``. When enabled, ``init`` builds
    ``ImGui``; the user calls ``ImGui.frame()`` from ``App.update(dt)``
    after ``renderer.flush_all`` and before ``window.end_drawing()``
    (inside the drawing block, without scene traversal).
    """

    enabled: bool = False
    """Whether the ImGui service is enabled."""

    dark_style: bool = True
    """Use the built-in ImGui dark style."""

    no_ini: bool = True
    """Disable creation of the ``imgui.ini`` file."""

    def validate(self) -> None:
        """Validates the ImGui fields (currently always considered valid)."""
        return


@dataclass(slots=True)
class AudioConfig:
    """Optional configuration for the audio service (SFX + music + spatial).

    Active only if ``enabled`` is ``True``. When enabled, ``init`` builds
    ``Audio`` via :func:`build_audio_service` and adds it to ``App``
    (device init happens in ``on_attach``).
    """

    enabled: bool = False
    """Whether the audio service is enabled."""

    master_volume: float = 1.0
    """Master volume in the ``[0.0, 1.0]`` range."""

    sfx_volume: float = 1.0
    """SFX volume in the ``[0.0, 1.0]`` range."""

    music_volume: float = 1.0
    """Music volume in the ``[0.0, 1.0]`` range."""

    assets_path: str = "./data/audio"
    """Path to the directory containing audio assets."""

    max_voices: int = 32
    """Maximum number of voices that can play simultaneously."""

    spatial_min_distance: float = 50.0
    """Minimum distance (pixels) for spatial audio (full volume)."""

    spatial_max_distance: float = 800.0
    """Maximum distance (pixels) for spatial audio (inaudible)."""

    spatial_rolloff: float = 1.0
    """Rolloff factor for spatial audio (``> 0``)."""

    def validate(self) -> None:
        """Validates the audio fields and raises ``ValueError`` if invalid.

        Raises:
            ValueError: If a volume is outside ``[0.0, 1.0]``,
                ``max_voices <= 0``, ``spatial_min_distance < 0``,
                ``spatial_max_distance <= spatial_min_distance``,
                ``spatial_rolloff <= 0``, or ``assets_path`` is empty.
        """
        for name, value in (
            ("master_volume", self.master_volume),
            ("sfx_volume", self.sfx_volume),
            ("music_volume", self.music_volume),
        ):
            if value < 0.0 or value > 1.0:
                raise ValueError(f"audio.{name} must be in [0, 1]")
        if self.max_voices <= 0:
            raise ValueError("audio.max_voices must be > 0")
        if self.spatial_min_distance < 0:
            raise ValueError("audio.spatial_min_distance must be >= 0")
        if self.spatial_max_distance <= self.spatial_min_distance:
            raise ValueError(
                "audio.spatial_max_distance must be > audio.spatial_min_distance"
            )
        if self.spatial_rolloff <= 0:
            raise ValueError("audio.spatial_rolloff must be > 0")
        if not self.assets_path:
            raise ValueError("audio.assets_path must not be empty")


@dataclass(slots=True)
class AppConfig:
    """Top-level application configuration.

    Collects window, timing, logging, and optional service settings, and
    supports loading from JSON files or dicts with full field validation.
    """

    title: str = "Plyunit Game"
    """Application title."""

    window_width: int = 800
    """Application window width in pixels."""

    window_height: int = 600
    """Application window height in pixels."""

    target_fps: int = 60
    """
    Desired frames per second. A value of 0 means no FPS limit.
    """

    fixed_update_hz: int = 60
    """
    Fixed update frequency for game logic, in Hertz. A value of 0 means
    no fixed update.
    """

    max_frame_delta_time: float = 0.25
    """
    Maximum time between frames, in seconds.
    """

    max_substeps_per_frame: int = 5
    """
    Maximum number of fixed update substeps executed per frame to prevent
    a spiral of death.
    """

    background_color: ColorType = (245, 245, 245, 255)
    """Application window background color."""

    log_level: str = "INFO"
    """Root logging level (e.g. ``"INFO"``, ``"DEBUG"``)."""

    log_file_path: str | None = None
    """Log file path. ``None`` means logging is not configured automatically."""

    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    """Optional physics configuration. Active only if ``physics.enabled``."""

    imgui: ImGuiConfig = field(default_factory=ImGuiConfig)
    """Optional ImGui configuration. Active only if ``imgui.enabled``."""

    audio: AudioConfig = field(default_factory=AudioConfig)
    """Optional audio configuration. Active only if ``audio.enabled``."""

    def validate(self) -> None:
        """Validates all ``AppConfig`` fields (including sub-configs).

        Raises:
            ValueError: If any field has an invalid value (window size,
                ``target_fps``, ``fixed_update_hz``, ``max_frame_delta_time``,
                ``max_substeps_per_frame``, ``log_level``, or the related
                sub-configs).
        """
        if self.window_width <= 0 or self.window_height <= 0:
            raise ValueError("window size must be greater than zero")
        if self.target_fps < 0:
            raise ValueError("target_fps must be >= 0")
        if self.fixed_update_hz <= 0:
            raise ValueError("fixed_update_hz must be > 0")
        if self.max_frame_delta_time <= 0:
            raise ValueError("max_frame_delta_time must be > 0")
        if self.max_substeps_per_frame <= 0:
            raise ValueError("max_substeps_per_frame must be > 0")
        if not self.log_level:
            raise ValueError("log_level must not be empty")
        self.physics.validate()
        self.imgui.validate()
        self.audio.validate()

    @classmethod
    def from_file(cls, path: str) -> Self:
        """Loads configuration from a JSON file.

        Args:
            path: Path to the JSON file.

        Returns:
            Self: A validated ``AppConfig`` instance.

        Raises:
            ValueError: If loading or validating the file fails.
        """
        try:
            return cls.from_dict(read_json(path))
        except Exception as e:
            raise ValueError(f"Failed to load AppConfig from file: {e}") from e

    @classmethod
    def from_dict(cls, config_dict: dict) -> Self:
        """Loads configuration from a dictionary.

        ``physics`` / ``imgui`` / ``audio`` may be either config objects or
        nested dicts, which are converted automatically.

        Args:
            config_dict: Dictionary containing ``AppConfig`` fields.

        Returns:
            Self: A validated ``AppConfig`` instance.

        Raises:
            ValueError: If a field is invalid or has the wrong type.
        """
        try:
            data = dict(config_dict)
            physics = data.get("physics")
            if isinstance(physics, dict):
                data["physics"] = PhysicsConfig(**physics)
            imgui = data.get("imgui")
            if isinstance(imgui, dict):
                data["imgui"] = ImGuiConfig(**imgui)
            audio = data.get("audio")
            if isinstance(audio, dict):
                data["audio"] = AudioConfig(**audio)
            instance = cls(**data)
            instance.validate()
            return instance
        except Exception as e:
            raise ValueError(f"Failed to create AppConfig from dict: {e}") from e

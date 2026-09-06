"""AnimationController component (plays AnimationClips on a SpriteRenderer)."""

from plyunit.assets.animations import AnimationClip, Animations
from plyunit.core.components.component import Component
from plyunit.events import Signal


class AnimationController(Component):
    """Component that plays an ``AnimationClip`` on a ``SpriteRenderer``.

    Fetches the clip from the ``Animations`` service, advances frames based on
    ``dt * clip.speed``, and syncs the ``SpriteRenderer`` every frame. Emits the
    ``finished`` signal when a non-looping clip completes.
    """

    updates = True

    def __init__(
        self, clip_name: str, frame_index: int = 0, group: str | None = None
    ) -> None:
        """Initializes the controller for a specific clip.

        Args:
            clip_name: Name of the initial clip.
            frame_index: Initial frame index (default ``0``).
            group: Optional clip group; if set, only clips in this group
                may be ``play``ed.
        """
        super().__init__("AnimationController")
        self.current_clip_name = clip_name
        self.frame_index = frame_index
        self.frame_time = 0.0
        self.playing = False

        # group is optional, if set, the component will only play clips that belong
        # to the group
        self.group = group

        # Emitted once when a non-looping clip reaches its last frame and stops.
        # Args: (clip_name: str, controller: AnimationController)
        self.finished = Signal("animation_finished")

    def play(self, clip_name: str | None = None, restart: bool = False) -> None:
        """Starts playing a clip.

        Args:
            clip_name: Name of the clip. ``None`` → use ``current_clip_name``.
            restart: ``True`` to force-reset frame_index to 0.

        Raises:
            ValueError: If neither ``clip_name`` nor ``current_clip_name`` is set.
            KeyError: If the clip is not found or is not in the ``group``.
        """

        if not clip_name and not self.current_clip_name:
            raise ValueError("animation clip name is not set")

        if not clip_name:
            clip_name = self.current_clip_name

        # Check that clip_name exists in the Animations service (not None),
        # and also check whether clip_name belongs to the group
        animations = self.unit.one(Animations)
        if self.group and not animations.is_clip_in_group(clip_name, self.group):
            raise KeyError(
                f"animation clip '{clip_name}' not found in group '{self.group}'"
            )
        elif not animations.get_clip(clip_name):
            raise KeyError(f"animation clip '{clip_name}' not found")

        should_reset = self.current_clip_name != clip_name or restart
        self.current_clip_name = clip_name
        if should_reset:
            self.frame_index = 0
            self.frame_time = 0.0
        self.playing = True

    def stop(self) -> None:
        """Stops playback and resets to the initial state (frame 0, idle)."""
        self.playing = False
        # self.current_clip_name = None
        self.frame_index = 0
        self.frame_time = 0.0

    def pause(self) -> None:
        """Pauses playback (keeps the current frame)."""
        self.playing = False

    def resume(self) -> None:
        """Resumes playback if there is an active clip."""
        if self.current_clip_name is not None:
            self.playing = True

    def is_playing(self, name: str | None = None) -> bool:
        """Checks whether a clip is playing.

        Args:
            name: Name of the clip to check (``None`` → check whether any
                clip is playing).

        Returns:
            bool: ``True`` if the clip is playing.
        """
        if not self.playing:
            return False
        if name is None:
            return True
        return self.current_clip_name == name

    def on_attach(self) -> None:
        """Lifecycle hook: validates that a ``SpriteRenderer`` exists on the same
        unit."""
        from .sprite import SpriteRenderer

        if not self.unit.has_component(SpriteRenderer):
            raise ValueError(
                "AnimationComponent requires SpriteComponent to be attached to the "
                "same unit"
            )

        self.sprite = self.unit[SpriteRenderer]

    def on_destroy(self) -> None:
        """Lifecycle hook: releases the reference to the ``SpriteRenderer``."""
        super().on_destroy()
        # pyrefly: ignore [bad-assignment]
        # Unsign sprite
        self.sprite = None

    def update(self, dt: float) -> None:
        """Advances the animation by ``dt`` seconds and syncs the ``SpriteRenderer``.

        Args:
            dt: Fixed-step delta time in seconds.
        """
        clip = self.current_clip()
        if not self.playing or clip is None:
            return

        self.frame_time += dt * clip.speed
        frame_count = len(clip.frames)

        while self.frame_time >= clip.frames[self.frame_index].duration:
            self.frame_time -= clip.frames[self.frame_index].duration

            if self.frame_index < frame_count - 1:
                self.frame_index += 1
                continue

            if clip.loop:
                self.frame_index = 0
                continue

            self.frame_index = frame_count - 1
            self.frame_time = 0.0
            self.playing = False
            clip_name = self.current_clip_name
            self.finished.emit(clip_name, self)
            bus = self.unit.one_or_none("@EventBus", scope="global")
            if bus is not None:
                bus.publish(
                    "animation.finished",
                    name=clip_name,
                    unit=self.unit,
                    controller=self,
                )
            break

        self._sync_sprite_renderer()

    def current_clip(self) -> AnimationClip | None:
        """Returns the currently active ``AnimationClip``, or ``None``."""
        if self.current_clip_name is None:
            return None
        return self.unit.one(Animations).get_clip(self.current_clip_name)

    def _sync_sprite_renderer(self) -> None:
        """Internal hook: syncs the current frame to the ``SpriteRenderer``."""
        clip = self.current_clip()
        if clip is None or not self.sprite:
            return

        frame = clip.frames[self.frame_index]
        if frame.texture is not None:
            self.sprite.set_texture(texture=frame.texture)
            self.sprite.set_source_rect(frame.source_rect)
        elif frame.asset_id is not None:
            self.sprite.set_texture(asset_key=frame.asset_id)
            self.sprite.set_source_rect(frame.source_rect)

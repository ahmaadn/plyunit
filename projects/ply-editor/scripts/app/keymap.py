from __future__ import annotations

import plyunit
from scripts.app import events


def poll_shortcuts(
    bus: plyunit.EventBus,
    *,
    ui: plyunit.ImGui,
    input_service: plyunit.Input,
) -> None:
    """Publish intents for global shortcuts; call once per frame.

    Args:
        bus: The event bus used to publish the intent.
        ui: The engine ImGui service (keyboard capture query).
        input_service: The engine input service (mapped actions).
    """
    if ui.want_capture_keyboard():
        return
    if input_service.is_down("ctrl") and input_service.is_pressed(events.APP_SAVE):
        bus.publish(events.APP_SAVE)


__all__ = ["poll_shortcuts"]

from imgui_bundle import imgui

ELLIPSIS = "..."


def elide_text(text: str, max_width: float) -> str:
    """Shorten ``text`` with an ellipsis so it renders within ``max_width``.

    Args:
        text: Original label text.
        max_width: Maximum rendered width in pixels.

    Returns:
        The original text if it fits, otherwise a truncated version.
    """
    if imgui.calc_text_size(text).x <= max_width:
        return text

    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if imgui.calc_text_size(text[:mid] + ELLIPSIS).x <= max_width:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + ELLIPSIS


def text_width(text: str) -> float:
    """Measure text with the current ImGui font (needs an active frame)."""
    return float(imgui.calc_text_size(text).x)


def set_tooltip(text: str):
    """
    Displays a tooltip for the most recently submitted UI item if it is currently
    hovered.
    """
    if imgui.is_item_hovered():
        imgui.set_tooltip(text)

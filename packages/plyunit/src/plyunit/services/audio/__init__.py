"""Portable audio schemas, playback identifiers, and 2D spatial math.

Device and native resource ownership are implemented by audio integrations.
Audio is resolved lazily through the public facade; importing this package
never imports or selects a backend.
"""

from typing import TYPE_CHECKING

from plyunit._lazy import create_lazy_loader

from ._types import SoundBankConfig, SoundBankEntry, VoiceId
from .spatial import compute_spatial

if TYPE_CHECKING:
    from plyunit.backends.integrations import Audio
    from plyunit.backends.ports.audio import IAudio

__all__ = [
    "Audio",
    "IAudio",
    "SoundBankConfig",
    "SoundBankEntry",
    "VoiceId",
    "compute_spatial",
]


_LAZY_MODULES = {
    "Audio": "plyunit.backends.integrations",
    "IAudio": "plyunit.backends.ports.audio",
}


__getattr__, __dir__ = create_lazy_loader(
    package_name=__name__,
    lazy_modules={
        "Audio": "plyunit.backends.integrations",
        "IAudio": "plyunit.backends.ports.audio",
    },
    global_dict=globals(),
    all_exports=__all__,
)

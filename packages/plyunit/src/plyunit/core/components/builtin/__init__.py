"""Builtin components: sprite, animator, audio source, particle.

Exports ``SpriteRenderer``, ``AnimationController``, ``AudioSource``, and
``ParticleEmitter``, ready to be attached to a ``Unit``.
"""

from .animator import AnimationController as AnimationController
from .audio_source import AudioSource as AudioSource
from .particle import ParticleEmitter as ParticleEmitter
from .sprite import SpriteRenderer as SpriteRenderer

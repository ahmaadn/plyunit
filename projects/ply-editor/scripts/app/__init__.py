"""Application layer: shared state hub, event-bus intents, and shortcut mapping.

Dependencies flow from the UI here, and from here into services and
state: ``context`` owns the shared state hub; ``events`` lists the
intent topics published on the event bus; ``keymap`` turns global
keyboard shortcuts into those intents.
"""

"""Backend-neutral engine services and shared service data.

Concrete backend services live under ``backends.integrations`` and implement
contracts in ``backends.ports``. Services attach to the active application
through the global unit registry.
"""

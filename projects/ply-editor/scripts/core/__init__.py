"""Pure domain layer: exclude rules, file classification, tree model, and scan results.

No ImGui, no I/O, no services. All types are dataclasses or enums;
``exclude`` compiles glob patterns, ``file_kind`` classifies file roles,
``file_tree`` defines the tree model for the explorer, and ``scan``
holds the result model produced by a background folder walk.
"""

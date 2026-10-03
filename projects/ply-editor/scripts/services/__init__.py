"""Service layer: access to the world outside the editor's process.

Dialogs wrap native Tk file/folder pickers. ``scan`` and
``scan_worker`` handle disk traversal, ``file_tree`` builds the
explorer model from scan results, ``assets`` loads indexes into
the engine asset store, and ``json_io`` provides safe atomic
read/write for every config file.
"""

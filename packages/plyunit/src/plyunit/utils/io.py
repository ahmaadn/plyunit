"""JSON / file IO helpers."""

import json
from pathlib import Path


def read_json(path: str | Path) -> dict:
    """Read JSON data from a file and return it as a Python object.

    Args:
        path: Path to the JSON file (str or ``Path``).

    Returns:
        object: The Python object representing the JSON contents.
    """
    with open(path) as f:
        return json.load(f)


def write_json(path: str | Path, data: object) -> None:
    """Write a Python object to a file as JSON.

    Args:
        path: Destination file path (str or ``Path``).
        data: Python object to serialize to JSON.
    """
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

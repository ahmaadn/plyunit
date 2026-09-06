"""Encoders and decoders for tile array formats used by tilemap data.

Supports the built-in formats: ``array`` (JSON native), ``csv``, and
``base64_zlib``. Custom decoders/encoders can be registered via
:data:`DECODER_REGISTRY` and :data:`ENCODER_REGISTRY`.
"""

from __future__ import annotations

import base64
import struct
import zlib
from collections.abc import Callable

type RawLayerData = str | list[int]
"""Raw representation of a single tile layer: an encoded string or a list of ints."""
type DecoderFn = Callable[[RawLayerData], list[int]]
"""Decoder function type: takes :data:`RawLayerData` and returns a list of ints."""
type EncoderFn = Callable[[list[int]], RawLayerData]
"""Encoder function type: takes a list of ints and returns :data:`RawLayerData`."""


# ---------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------


def decode_array(data: RawLayerData) -> list[int]:
    """Array decoder — passthrough when data is already a list of ints.

    If ``data`` is a CSV-like string, it is split on commas.

    Args:
        data: Raw layer data (list of ints or a string).

    Returns:
        list[int]: The decoded list of GIDs.
    """
    if isinstance(data, list):
        return data
    return [int(x) for x in str(data).split(",") if x.strip()]


def decode_csv(data: RawLayerData) -> list[int]:
    """Decodes a CSV string (comma-separated) into a list of integers.

    Args:
        data: Raw layer data (list of ints or a CSV string).

    Returns:
        list[int]: The decoded list of GIDs.
    """
    if isinstance(data, list):
        return data
    return [int(x) for x in str(data).split(",") if x.strip()]


def decode_base64_zlib(data: RawLayerData) -> list[int]:
    """Decodes base64+zlib (little-endian uint32) into a list of integers.

    Args:
        data: Raw layer data (list of ints or a base64+zlib string).

    Returns:
        list[int]: The decoded list of GIDs.

    Raises:
        zlib.error: If the string cannot be decompressed.
        struct.error: If the decompressed length is not a multiple of 4 bytes.
    """
    if isinstance(data, list):
        return data
    compressed = base64.b64decode(str(data))
    binary_data = zlib.decompress(compressed)
    count = len(binary_data) // 4
    return list(struct.unpack(f"<{count}I", binary_data))


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------


def encode_array(data: list[int]) -> list[int]:
    """Array encoder — passthrough, returns the list of integers unchanged.

    Args:
        data: The list of GIDs to encode.

    Returns:
        list[int]: The same list as the input.
    """
    return data


def encode_csv(data: list[int]) -> str:
    """Encodes a list of integers into a CSV string (comma-separated).

    Args:
        data: The list of GIDs to encode.

    Returns:
        str: The CSV representation of the list.
    """
    return ",".join(map(str, data))


def encode_base64_zlib(data: list[int]) -> str:
    """Encodes a list of integers into base64 of zlib (little-endian uint32).

    Args:
        data: The list of GIDs to encode.

    Returns:
        str: The base64 string produced by compression and encoding.
    """
    binary_data = struct.pack(f"<{len(data)}I", *data)
    compressed = zlib.compress(binary_data)
    return base64.b64encode(compressed).decode("utf-8")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DECODER_REGISTRY: dict[str, DecoderFn] = {
    "array": decode_array,
    "csv": decode_csv,
    "base64_zlib": decode_base64_zlib,
}

ENCODER_REGISTRY: dict[str, EncoderFn] = {
    "array": encode_array,
    "csv": encode_csv,
    "base64_zlib": encode_base64_zlib,
}


def get_decoder(name: str) -> DecoderFn:
    """Gets the decoder for a format name.

    Args:
        name: Encoding name (e.g. ``"csv"``, ``"base64_zlib"``).

    Returns:
        DecoderFn: The registered decoder function.

    Raises:
        KeyError: If the format is unknown.
    """
    if name not in DECODER_REGISTRY:
        raise KeyError(f"Encoding tidak dikenal: '{name}'")
    return DECODER_REGISTRY[name]


def get_encoder(name: str) -> EncoderFn:
    """Gets the encoder for a format name.

    Args:
        name: Encoding name (e.g. ``"csv"``, ``"base64_zlib"``).

    Returns:
        EncoderFn: The registered encoder function.

    Raises:
        KeyError: If the format is unknown.
    """
    if name not in ENCODER_REGISTRY:
        raise KeyError(f"Encoding tidak dikenal: '{name}'")
    return ENCODER_REGISTRY[name]


def register_decoder(name: str, fn: DecoderFn) -> None:
    """Registers a custom decoder in the global registry.

    Args:
        name: The new encoding name.
        fn: Decoder function satisfying the :data:`DecoderFn` contract.
    """
    DECODER_REGISTRY[name] = fn


def register_encoder(name: str, fn: EncoderFn) -> None:
    """Registers a custom encoder in the global registry.

    Args:
        name: The new encoding name.
        fn: Encoder function satisfying the :data:`EncoderFn` contract.
    """
    ENCODER_REGISTRY[name] = fn

"""Isolated service registry and native-call fixtures for asset regression tests."""

from __future__ import annotations

import importlib

import pytest

from asset_fakes import FakeGPU, FakeImages
from plyunit.backends.integrations.raylib.assets import Assets
from plyunit.core.units.unit_registry import UnitRegistry


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> UnitRegistry:
    registry = UnitRegistry()
    module = importlib.import_module("plyunit.core.units.unit")
    monkeypatch.setattr(module, "units", registry)
    return registry


@pytest.fixture
def gpu(monkeypatch: pytest.MonkeyPatch) -> FakeGPU:
    gpu = FakeGPU()
    module = importlib.import_module("plyunit.backends.integrations.raylib.assets")
    monkeypatch.setattr(module, "pr", gpu.native_module())
    return gpu


@pytest.fixture
def images() -> FakeImages:
    return FakeImages()


@pytest.fixture
def manager(tmp_path, gpu: FakeGPU, images: FakeImages) -> Assets:
    return Assets(tmp_path, image_processor=images)

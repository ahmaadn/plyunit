import pytest

from plyunit.core import app as app_module


def test_audio_config_defaults() -> None:
    cfg = app_module.AppConfig()
    assert cfg.audio.enabled is False
    assert cfg.audio.master_volume == 1.0
    assert cfg.audio.max_voices == 32


def test_app_config_from_dict_nested_audio() -> None:
    cfg = app_module.AppConfig.from_dict(
        {
            "title": "t",
            "audio": {
                "enabled": True,
                "master_volume": 0.5,
                "max_voices": 8,
            },
        }
    )
    assert cfg.audio.enabled is True
    assert cfg.audio.master_volume == 0.5
    assert cfg.audio.max_voices == 8


def test_audio_config_validate_rejects_bad_volumes() -> None:
    with pytest.raises(ValueError, match="master_volume"):
        app_module.AudioConfig(master_volume=1.5).validate()


def test_audio_config_validate_spatial_distances() -> None:
    with pytest.raises(ValueError, match="spatial_max_distance"):
        app_module.AudioConfig(
            spatial_min_distance=100.0, spatial_max_distance=50.0
        ).validate()

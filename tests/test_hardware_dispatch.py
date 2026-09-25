import pytest
from hardware import detect_hardware, get_recommended_settings

def test_detect_hardware():
    hw = detect_hardware()
    assert "platform" in hw
    assert "gpu_type" in hw
    assert "recommended_engine" in hw
    assert hw["gpu_type"] in {"apple_metal", "nvidia_cuda", "cpu"}
    assert isinstance(hw["recommended_engine"], str)

def test_get_recommended_settings():
    settings = get_recommended_settings()
    assert "threads" in settings
    assert "batch_size" in settings
    assert "fastest_option" in settings
    assert settings["threads"] >= 1

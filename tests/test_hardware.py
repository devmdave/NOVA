"""Tests for hardware capability detection."""
import pytest
from app.hardware.capabilities import HardwareCapabilities, detect


class TestHardwareCapabilities:
    def test_detect_returns_instance(self):
        caps = detect()
        assert isinstance(caps, HardwareCapabilities)

    def test_cpu_name_non_empty(self):
        caps = detect()
        assert caps.cpu_name
        assert len(caps.cpu_name) > 0

    def test_cpu_cores_positive(self):
        caps = detect()
        assert caps.cpu_cores >= 1

    def test_ram_non_negative(self):
        caps = detect()
        # RAM should be > 0 on any real machine; allow 0 in CI environments
        assert caps.ram_gb >= 0.0

    def test_platform_name_set(self):
        caps = detect()
        assert caps.platform_name in ("Windows", "Linux", "Darwin", "")

    def test_gpus_is_list(self):
        caps = detect()
        assert isinstance(caps.gpus, list)

    def test_has_gpu_reflects_gpus(self):
        caps = detect()
        assert caps.has_gpu == (len(caps.gpus) > 0)

    def test_primary_gpu_none_when_no_gpus(self):
        # Construct a capabilities object with no GPUs manually
        caps = HardwareCapabilities(
            cpu_name="Test CPU", cpu_cores=4, ram_gb=8.0, gpus=[], platform_name="Windows"
        )
        assert caps.primary_gpu is None
        assert not caps.has_gpu

    def test_summary_returns_string(self):
        caps = detect()
        summary = caps.summary()
        assert isinstance(summary, str)
        assert "CPU" in summary
        assert "RAM" in summary
        assert "GPU" in summary

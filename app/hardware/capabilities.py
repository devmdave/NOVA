"""
Hardware capability detection for NOVA.

Uses only stdlib — no third-party packages required.
GPU detection degrades gracefully when driver tools are absent.

Future backends can call ``detect()`` at startup to decide which
pipeline, dtype, or device to use.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("nova.hardware")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GpuInfo:
    """Information about a single GPU."""
    name: str
    vendor: str                      # "NVIDIA", "AMD", "Intel", "Apple", "Unknown"
    vram_gb: Optional[float] = None  # None when not detectable


@dataclass(frozen=True)
class HardwareCapabilities:
    """Snapshot of the host machine's hardware relevant to local AI inference."""

    cpu_name: str
    cpu_cores: int            # logical cores (includes hyperthreading)
    ram_gb: float
    gpus: list[GpuInfo] = field(default_factory=list)
    platform_name: str = ""   # "Windows", "Linux", "Darwin"

    @property
    def has_gpu(self) -> bool:
        return len(self.gpus) > 0

    @property
    def primary_gpu(self) -> Optional[GpuInfo]:
        return self.gpus[0] if self.gpus else None

    def summary(self) -> str:
        gpu_parts = [f"{g.name} ({g.vendor}, {f'{g.vram_gb:.1f} GB VRAM' if g.vram_gb else 'VRAM unknown'})"
                     for g in self.gpus]
        gpu_str = "; ".join(gpu_parts) if gpu_parts else "None detected"
        return (
            f"CPU: {self.cpu_name} ({self.cpu_cores} cores) | "
            f"RAM: {self.ram_gb:.1f} GB | "
            f"GPU: {gpu_str}"
        )


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _cpu_name() -> str:
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return name.strip()
    except Exception:
        pass
    return platform.processor() or "Unknown CPU"


def _ram_gb() -> float:
    try:
        if platform.system() == "Windows":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
        else:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 ** 2), 1)
    except Exception:
        pass
    return 0.0


def _detect_nvidia_gpus() -> list[GpuInfo]:
    """Query nvidia-smi for NVIDIA GPU names and VRAM."""
    gpus: list[GpuInfo] = []
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                name = parts[0] if parts else "Unknown NVIDIA GPU"
                try:
                    vram_gb = round(int(parts[1]) / 1024, 1) if len(parts) > 1 else None
                except ValueError:
                    vram_gb = None
                gpus.append(GpuInfo(name=name, vendor="NVIDIA", vram_gb=vram_gb))
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return gpus


def _detect_amd_gpus() -> list[GpuInfo]:
    """Query rocm-smi for AMD GPU names (Linux/ROCm only)."""
    gpus: list[GpuInfo] = []
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "GPU" in line and ":" in line:
                    name = line.split(":", 1)[-1].strip()
                    gpus.append(GpuInfo(name=name or "AMD GPU", vendor="AMD"))
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return gpus


def _detect_apple_gpus() -> list[GpuInfo]:
    """Detect Apple Silicon MPS GPU via platform info."""
    if platform.system() == "Darwin" and platform.processor() == "arm":
        return [GpuInfo(name="Apple Silicon GPU", vendor="Apple")]
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect() -> HardwareCapabilities:
    """Detect and return the current machine's hardware capabilities.

    Gracefully degrades — partial information is always returned even when
    some detection steps fail (e.g., driver tools not installed).
    """
    logger.debug("Detecting hardware capabilities...")

    cpu = _cpu_name()
    cores = os.cpu_count() or 1
    ram = _ram_gb()

    gpus: list[GpuInfo] = []
    gpus.extend(_detect_nvidia_gpus())
    if not gpus:
        gpus.extend(_detect_amd_gpus())
    if not gpus:
        gpus.extend(_detect_apple_gpus())

    caps = HardwareCapabilities(
        cpu_name=cpu,
        cpu_cores=cores,
        ram_gb=ram,
        gpus=gpus,
        platform_name=platform.system(),
    )
    logger.info("Hardware detected: %s", caps.summary())
    return caps

import os
import sys
import platform
import subprocess
from typing import Dict, Any

def _has_nvidia_cuda() -> bool:
    """Checks if an active Nvidia GPU is accessible."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1.5
        )
        if res.returncode == 0 and res.stdout.strip():
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    
    # Optional check if torch is already imported or available
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except ImportError:
        pass
    return False

def _is_apple_silicon() -> bool:
    """Checks if running on Apple Silicon (M1/M2/M3/M4) with Metal acceleration."""
    if sys.platform == "darwin":
        machine = platform.machine().lower()
        if "arm" in machine or "aarch64" in machine:
            return True
    return False

def detect_hardware() -> Dict[str, Any]:
    """
    Auto-detects host system architecture, GPU accelerators, and optimal engine.
    Works universally across macOS Apple Silicon, Windows/Linux Nvidia CUDA, and CPU laptops.
    """
    plat = sys.platform
    cpu_cores = os.cpu_count() or 4
    
    if _is_apple_silicon():
        return {
            "platform": plat,
            "architecture": platform.machine(),
            "gpu_type": "apple_metal",
            "gpu_name": "Apple Silicon (Metal Unified Memory)",
            "recommended_engine": "local_metal",
            "cpu_cores": cpu_cores,
            "metal_supported": True,
            "description": "Apple Silicon Metal Acceleration (Zero-copy unified VRAM)"
        }
    
    if _has_nvidia_cuda():
        return {
            "platform": plat,
            "architecture": platform.machine(),
            "gpu_type": "nvidia_cuda",
            "gpu_name": "Nvidia CUDA Device",
            "recommended_engine": "local_cuda",
            "cpu_cores": cpu_cores,
            "metal_supported": False,
            "description": "Nvidia CUDA Core Acceleration"
        }
        
    return {
        "platform": plat,
        "architecture": platform.machine(),
        "gpu_type": "cpu",
        "gpu_name": "None (Host CPU)",
        "recommended_engine": "cloud_api",
        "cpu_cores": cpu_cores,
        "metal_supported": False,
        "description": "Host CPU (Recommended: Cloud API or Colab for sub-2s latency)"
    }

def get_recommended_settings() -> Dict[str, Any]:
    """
    Returns optimal threading, batching, and speed recommendations based on detected hardware.
    """
    hw = detect_hardware()
    cpu_cores = hw["cpu_cores"]
    
    if hw["gpu_type"] == "apple_metal":
        return {
            "threads": min(cpu_cores, 8),
            "batch_size": 4,
            "fastest_option": "local_metal",
            "ocr_model": "glm-ocr",
            "grading_model": "llama3.2:3b",
            "expected_latency_sec": 3.0
        }
    elif hw["gpu_type"] == "nvidia_cuda":
        return {
            "threads": min(cpu_cores, 8),
            "batch_size": 8,
            "fastest_option": "local_cuda",
            "ocr_model": "glm-ocr",
            "grading_model": "llama3.2:3b",
            "expected_latency_sec": 2.0
        }
    else:
        # CPU host: Cloud API (Mistral/Gemini) is 1.5s vs 120s on CPU
        return {
            "threads": max(1, cpu_cores // 2),
            "batch_size": 1,
            "fastest_option": "cloud_api",
            "ocr_model": "glm-ocr",
            "grading_model": "llama3.2:3b",
            "expected_latency_sec": 1.5
        }

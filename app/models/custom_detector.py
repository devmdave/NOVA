"""
Custom model discovery, architecture detection, and file validation.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from app.models.spec import ModelSpec, ModelStatus

logger = logging.getLogger("nova.models.custom_detector")

# Known diffusers pipeline mappings to architectures and runtimes
_PIPELINE_MAP: dict[str, tuple[str, str, float]] = {
    # _class_name: (architecture, runtime, min_vram_gb)
    "FluxPipeline": ("flux-1", "diffusers_flux", 16.0),
    "FluxImg2ImgPipeline": ("flux-1", "diffusers_flux", 16.0),
    "FluxInpaintPipeline": ("flux-1", "diffusers_flux", 16.0),
    "StableDiffusionXLPipeline": ("sdxl", "diffusers_sdxl", 8.0),
    "StableDiffusionXLImg2ImgPipeline": ("sdxl", "diffusers_sdxl", 8.0),
    "StableDiffusionXLInpaintPipeline": ("sdxl", "diffusers_sdxl", 8.0),
    "StableDiffusionPipeline": ("sd15", "diffusers_sd15", 4.0),
    "StableDiffusionImg2ImgPipeline": ("sd15", "diffusers_sd15", 4.0),
}


def detect_and_validate_custom_model(model_dir: str | Path) -> Tuple[Optional[ModelSpec], List[str]]:
    """Inspect a local directory, detect architecture/runtime, and validate required files.

    Returns:
        (ModelSpec, []) on success.
        (None, [error_messages]) on failure.
    """
    path = Path(model_dir).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        return None, ["Specified path does not exist or is not a directory."]

    index_file = path / "model_index.json"
    if not index_file.exists():
        logger.warning("Custom model detection failed for %s: missing model_index.json", path)
        return None, [
            "Unsupported model architecture/runtime — missing model_index.json pipeline index. "
            "NOVA requires a complete Diffusers pipeline directory, not standalone weight files."
        ]

    try:
        with open(index_file, "r", encoding="utf-8") as f:
            index_data = json.load(f)
    except Exception as exc:
        logger.warning("Corrupted model_index.json in %s: %s", path, exc)
        return None, [f"Unsupported model architecture/runtime — corrupted model_index.json: {exc}"]

    if not isinstance(index_data, dict) or "_class_name" not in index_data:
        return None, ["Unsupported model architecture/runtime — invalid model_index.json format."]

    class_name = index_data.get("_class_name", "")
    pipeline_info = _PIPELINE_MAP.get(class_name)

    if not pipeline_info:
        logger.warning("Unrecognized pipeline class '%s' in %s", class_name, path)
        return None, [
            f"Unsupported model architecture/runtime — pipeline '{class_name}' is not supported."
        ]

    architecture, runtime, min_vram = pipeline_info

    # Validate required subfolders/files declared in model_index.json
    missing_items: List[str] = []
    for key, value in index_data.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
            subfolder = value[0]
            if subfolder and subfolder != "null":
                subpath = path / subfolder
                if not subpath.exists():
                    missing_items.append(subfolder)

    if missing_items:
        return None, [
            f"Incomplete model directory: missing required components ({', '.join(missing_items)})."
        ]

    # Calculate model directory size in GB
    total_bytes = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                total_bytes += f.stat().st_size
    except Exception:
        pass
    size_gb = round(total_bytes / (1024 ** 3), 1)

    model_id = path.name.lower().replace(" ", "_")
    display_name = f"Custom {architecture.upper()} ({path.name})"

    spec = ModelSpec(
        model_id=model_id,
        display_name=display_name,
        description=f"Custom local model ({architecture.upper()}) discovered at {path}",
        source=str(path),
        architecture=architecture,
        runtime=runtime,
        license="Custom / Local",
        min_vram_gb=min_vram,
        recommended_vram_gb=min_vram + 4.0,
        model_size_gb=size_gb,
        precision="bfloat16" if architecture == "flux-1" else "fp16",
        capabilities=["text-to-image", "image-to-image", "inpainting"],
        supported_vendors=["NVIDIA", "AMD", "Apple"],
        default_width=1024 if architecture in ("flux-1", "sdxl") else 512,
        default_height=1024 if architecture in ("flux-1", "sdxl") else 512,
        steps_min=1,
        steps_default=4 if architecture == "flux-1" else 20,
        steps_max=50,
        guidance_default=0.0 if architecture == "flux-1" else 7.5,
        tags=["custom", architecture, "local"],
        status=ModelStatus.INSTALLED,
        is_custom=True,
    )

    return spec, []

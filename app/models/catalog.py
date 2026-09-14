"""
Official Model Catalog — separate catalogue of supported text-to-image models.

This catalog lists downloadable official models. It is distinct from the installed ModelRegistry.
"""
from __future__ import annotations

from typing import List, Optional
from app.models.spec import ModelSpec, ModelStatus


def get_official_catalog() -> List[ModelSpec]:
    """Return list of officially supported text-to-image models available for acquisition."""
    return [
        ModelSpec(
            model_id="flux-schnell",
            display_name="FLUX.1-schnell",
            description=(
                "A 12-billion parameter rectified flow transformer for state-of-the-art text-to-image generation. "
                "Generates high-fidelity 1024×1024 images in 1–4 steps."
            ),
            source="black-forest-labs/FLUX.1-schnell",
            architecture="flux-1",
            runtime="diffusers_flux",
            license="Apache 2.0",
            min_vram_gb=16.0,
            recommended_vram_gb=24.0,
            model_size_gb=23.8,
            precision="bfloat16",
            capabilities=["text-to-image", "image-to-image", "inpainting"],
            supported_vendors=["NVIDIA", "AMD", "Apple"],
            default_width=1024,
            default_height=1024,
            steps_min=1,
            steps_default=4,
            steps_max=20,
            guidance_default=0.0,
            tags=["flux", "official", "state-of-the-art"],
            status=ModelStatus.AVAILABLE,
        ),
        ModelSpec(
            model_id="sdxl-turbo",
            display_name="SDXL Turbo",
            description=(
                "Fast real-time text-to-image model based on SDXL architecture. "
                "Produces quality images in a single inference step with lower VRAM requirements."
            ),
            source="stabilityai/sdxl-turbo",
            architecture="sdxl",
            runtime="diffusers_sdxl",
            license="OpenRAIL-M",
            min_vram_gb=8.0,
            recommended_vram_gb=12.0,
            model_size_gb=6.9,
            precision="fp16",
            capabilities=["text-to-image", "image-to-image"],
            supported_vendors=["NVIDIA", "AMD", "Apple"],
            default_width=512,
            default_height=512,
            steps_min=1,
            steps_default=1,
            steps_max=10,
            guidance_default=0.0,
            tags=["sdxl", "fast", "official"],
            status=ModelStatus.AVAILABLE,
        ),
        ModelSpec(
            model_id="sd15",
            display_name="Stable Diffusion v1.5",
            description=(
                "Classic, highly compatible text-to-image model. Ideal for hardware with 4 GB VRAM."
            ),
            source="runwayml/stable-diffusion-v1-5",
            architecture="sd15",
            runtime="diffusers_sd15",
            license="CreativeML OpenRAIL-M",
            min_vram_gb=4.0,
            recommended_vram_gb=8.0,
            model_size_gb=4.0,
            precision="fp16",
            capabilities=["text-to-image", "image-to-image", "inpainting"],
            supported_vendors=["NVIDIA", "AMD", "Apple"],
            default_width=512,
            default_height=512,
            steps_min=10,
            steps_default=20,
            steps_max=50,
            guidance_default=7.5,
            tags=["sd15", "lightweight", "official"],
            status=ModelStatus.AVAILABLE,
        ),
    ]


def get_catalog_item(model_id: str) -> Optional[ModelSpec]:
    """Look up an official catalog entry by model_id."""
    for spec in get_official_catalog():
        if spec.model_id == model_id:
            return spec
    return None

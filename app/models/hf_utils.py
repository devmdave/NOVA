"""
Hugging Face model repository parsing and pre-flight metadata inspection.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Optional, Tuple
import requests

from app.models.custom_detector import _PIPELINE_MAP
from app.models.spec import ModelSpec, ModelStatus

logger = logging.getLogger("nova.models.hf_utils")

# Pattern for validating Hugging Face owner/repo identifier
_REPO_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+$")


def parse_hf_repo_id(input_str: str) -> Optional[str]:
    """Extract owner/repo identifier from string or Hugging Face URL.

    Examples:
        "black-forest-labs/FLUX.1-schnell" -> "black-forest-labs/FLUX.1-schnell"
        "https://huggingface.co/stabilityai/sdxl-turbo" -> "stabilityai/sdxl-turbo"
        "https://huggingface.co/runwayml/stable-diffusion-v1-5/tree/main" -> "runwayml/stable-diffusion-v1-5"
    """
    if not input_str:
        return None

    cleaned = input_str.strip()

    # Handle URLs
    if "huggingface.co/" in cleaned:
        parts = cleaned.split("huggingface.co/")[-1].strip("/").split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            candidate = f"{owner}/{repo}"
            if _REPO_ID_PATTERN.match(candidate):
                return candidate

    # Handle direct repo_id
    if _REPO_ID_PATTERN.match(cleaned):
        return cleaned

    return None


def fetch_hf_model_index(repo_id: str, timeout: float = 10.0) -> Tuple[Optional[dict], Optional[str]]:
    """Fetch model_index.json metadata from Hugging Face for pre-flight detection."""
    clean_id = parse_hf_repo_id(repo_id)
    if not clean_id:
        return None, f"Invalid Hugging Face model identifier: '{repo_id}'."

    url = f"https://huggingface.co/{clean_id}/raw/main/model_index.json"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            return None, f"Repository or model_index.json not found on Hugging Face ({clean_id})."
        if resp.status_code != 200:
            return None, f"Hugging Face HTTP error {resp.status_code} fetching model_index.json."

        data = resp.json()
        if not isinstance(data, dict):
            return None, "Corrupted model_index.json: not a valid JSON object."
        return data, None

    except requests.RequestException as exc:
        logger.warning("Failed to connect to Hugging Face for %s: %s", clean_id, exc)
        return None, f"Network error connecting to Hugging Face: {exc}"
    except Exception as exc:
        return None, f"Error parsing model_index.json: {exc}"


def inspect_hf_custom_model(repo_id: str, index_data: Optional[dict] = None) -> Tuple[Optional[ModelSpec], List[str]]:
    """Verify that a Hugging Face model repository is supported by NOVA before downloading.

    Returns:
        (ModelSpec, []) if supported.
        (None, [reasons]) if unsupported or error.
    """
    clean_id = parse_hf_repo_id(repo_id)
    if not clean_id:
        return None, [f"Invalid Hugging Face model identifier: '{repo_id}'."]

    if index_data is None:
        data, err = fetch_hf_model_index(clean_id)
        if err or data is None:
            return None, [err or "Failed to inspect model repository."]
    else:
        data = index_data

    class_name = data.get("_class_name", "")
    pipeline_info = _PIPELINE_MAP.get(class_name)

    if not pipeline_info:
        return None, [
            f"Unsupported model architecture: pipeline class '{class_name}' is not supported by NOVA. "
            f"Supported runtimes: FluxPipeline, StableDiffusionXLPipeline, StableDiffusionPipeline."
        ]

    architecture, runtime, min_vram = pipeline_info

    owner, repo_name = clean_id.split("/")
    model_id = repo_name.lower().replace(" ", "_").replace(".", "_")

    spec = ModelSpec(
        model_id=model_id,
        display_name=f"{architecture.upper()} ({clean_id})",
        description=f"Custom {architecture.upper()} model acquired from Hugging Face ({clean_id}).",
        source=clean_id,
        architecture=architecture,
        runtime=runtime,
        license="Hugging Face License",
        min_vram_gb=min_vram,
        recommended_vram_gb=min_vram + 4.0,
        model_size_gb=6.0,  # Estimated fallback size
        precision="fp16",
        capabilities=["text-to-image", "image-to-image"],
        is_custom=True,
        status=ModelStatus.AVAILABLE,
    )
    return spec, []

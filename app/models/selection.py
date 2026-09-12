"""
Model Selection Service — intelligently evaluates models against hardware.

Does not import GUI or hardware specifics (takes HardwareCapabilities as input).
Determines if models are compatible, why they aren't, and recommends the best one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.hardware.capabilities import HardwareCapabilities
from app.models.spec import ModelSpec

logger = logging.getLogger("nova.models.selection")


@dataclass
class ModelCompatibility:
    model_id: str
    is_compatible: bool
    reasons: list[str]


@dataclass
class ModelRecommendation:
    hardware: HardwareCapabilities
    evaluations: dict[str, ModelCompatibility]
    recommended_model_id: Optional[str]
    recommendation_reason: str


class ModelSelectionService:
    """Evaluates models against hardware to find the best compatible choice."""

    def evaluate(self, hardware: HardwareCapabilities, specs: list[ModelSpec]) -> ModelRecommendation:
        evaluations: dict[str, ModelCompatibility] = {}
        compatible_specs: list[ModelSpec] = []

        for spec in specs:
            is_compatible, reasons = self._check_compatibility(hardware, spec)
            evaluations[spec.model_id] = ModelCompatibility(
                model_id=spec.model_id,
                is_compatible=is_compatible,
                reasons=reasons,
            )
            if is_compatible:
                compatible_specs.append(spec)

        recommended_id, reason = self._recommend(hardware, compatible_specs)

        return ModelRecommendation(
            hardware=hardware,
            evaluations=evaluations,
            recommended_model_id=recommended_id,
            recommendation_reason=reason,
        )

    def _check_compatibility(self, hardware: HardwareCapabilities, spec: ModelSpec) -> tuple[bool, list[str]]:
        """Check if a model can run on the given hardware.
        Returns (is_compatible, list_of_reasons).
        """
        reasons = []
        is_compatible = True

        # Check GPU existence and vendor
        if spec.min_vram_gb > 0 or spec.supported_vendors:
            if not hardware.has_gpu:
                is_compatible = False
                reasons.append("Model requires a GPU, but none was detected.")
                return is_compatible, reasons

            primary_gpu = hardware.primary_gpu
            if primary_gpu:
                if spec.supported_vendors and primary_gpu.vendor not in spec.supported_vendors:
                    is_compatible = False
                    reasons.append(f"GPU vendor '{primary_gpu.vendor}' is not supported. Needs: {', '.join(spec.supported_vendors)}.")

                # Check VRAM
                if primary_gpu.vram_gb is not None:
                    if primary_gpu.vram_gb < spec.min_vram_gb:
                        is_compatible = False
                        reasons.append(
                            f"Insufficient VRAM: {primary_gpu.vram_gb:.1f} GB detected, "
                            f"{spec.min_vram_gb:.1f} GB required."
                        )
                    elif spec.recommended_vram_gb > 0 and primary_gpu.vram_gb < spec.recommended_vram_gb:
                        reasons.append(
                            f"VRAM is below recommended ({spec.recommended_vram_gb:.1f} GB). "
                            "Generation may be slow or unstable."
                        )
                else:
                    reasons.append("Could not detect GPU VRAM. Assuming compatible, but generation may fail if insufficient.")

        # Check System RAM against model size
        if spec.model_size_gb > 0:
            if hardware.ram_gb < spec.model_size_gb:
                is_compatible = False
                reasons.append(
                    f"Insufficient System RAM: {hardware.ram_gb:.1f} GB detected, "
                    f"model requires at least {spec.model_size_gb:.1f} GB to load into memory."
                )

        if not reasons:
            reasons.append("Hardware meets all requirements.")

        return is_compatible, reasons

    def _recommend(self, hardware: HardwareCapabilities, compatible_specs: list[ModelSpec]) -> tuple[Optional[str], str]:
        """Choose the best model from the compatible ones."""
        if not compatible_specs:
            return None, "No compatible models found for your hardware."

        if not hardware.has_gpu:
            # CPU only
            best = min(compatible_specs, key=lambda s: s.model_size_gb)
            return best.model_id, "Selected the smallest model for CPU generation."

        primary_gpu = hardware.primary_gpu
        assert primary_gpu is not None  # type narrowing

        vram = primary_gpu.vram_gb or 0.0

        # Filter to models where VRAM >= recommended, if any
        highly_recommended = [s for s in compatible_specs if s.recommended_vram_gb > 0 and vram >= s.recommended_vram_gb]
        
        if highly_recommended:
            # Pick the most capable one among those that fit perfectly (largest size)
            best = max(highly_recommended, key=lambda s: s.model_size_gb)
            return best.model_id, f"Your {primary_gpu.vendor} GPU meets the recommended {best.recommended_vram_gb:.1f} GB VRAM for this high-quality model."

        # Fallback to the largest compatible model that fits in min VRAM
        best = max(compatible_specs, key=lambda s: s.model_size_gb)
        if best.recommended_vram_gb > 0 and vram > 0:
            return best.model_id, f"Best available model that fits in your {vram:.1f} GB VRAM (recommended is {best.recommended_vram_gb:.1f} GB)."
        
        return best.model_id, "Best compatible model available."

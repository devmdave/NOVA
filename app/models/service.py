"""
ModelService — core application service for local model management, validation, and scanning.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from app.config.service import SettingsService
from app.models.custom_detector import detect_and_validate_custom_model
from app.models.errors import ModelNotFoundError
from app.models.registry import ModelRegistry
from app.models.spec import ModelSpec, ModelStatus
from app.models.acquisition import ModelAcquisitionService

logger = logging.getLogger("nova.models.service")


class ModelService(QObject):
    """Core service managing local models, validation states, scanning, and removal."""

    model_updated = Signal(ModelSpec)
    model_removed = Signal(str)
    registry_refreshed = Signal()

    def __init__(
        self,
        registry: ModelRegistry,
        store: LocalModelStore,
        settings_service: SettingsService,
        acquisition_service: Optional[ModelAcquisitionService] = None,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._store = store
        self._settings_service = settings_service
        self._acquisition_service = acquisition_service or ModelAcquisitionService(
            registry, store, settings_service
        )
        self._acquisition_service.download_finished.connect(self._on_download_finished)

    @property
    def acquisition(self) -> ModelAcquisitionService:
        return self._acquisition_service

    def _on_download_finished(self, model_id: str, success: bool, spec: Optional[ModelSpec], error: str) -> None:
        if success and spec:
            if spec.is_custom:
                self.save_custom_models()
            self.model_updated.emit(spec)
            self.registry_refreshed.emit()

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @property
    def store(self) -> LocalModelStore:
        return self._store

    def get_all_models(self) -> List[ModelSpec]:
        """Return all registered model specifications."""
        return self._registry.list_all()

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        """Fetch model spec by ID."""
        return self._registry.get_or_none(model_id)

    def validate_model(self, model_id: str) -> Tuple[bool, List[str]]:
        """Run file inspection and validation on a model.

        Transitions state: AVAILABLE -> VALIDATING -> READY or INVALID.
        """
        spec = self.get_model(model_id)
        if not spec:
            return False, [f"Model '{model_id}' is not registered."]

        spec.status = ModelStatus.VALIDATING
        self.model_updated.emit(spec)

        problems: List[str] = []

        if spec.is_custom:
            _, problems = detect_and_validate_custom_model(spec.source)
        else:
            problems = self._store.validate_installation(spec)

        if problems:
            spec.status = ModelStatus.INVALID
            spec.error_message = " · ".join(problems)
            logger.warning("Validation failed for model '%s': %s", model_id, spec.error_message)
        else:
            spec.status = ModelStatus.READY
            spec.error_message = None
            logger.info("Validation passed for model '%s' (Status: READY).", model_id)

        self.model_updated.emit(spec)
        return spec.status == ModelStatus.READY, problems

    def rescan_model(self, model_id: str) -> Tuple[ModelStatus, List[str]]:
        """Re-scan disk path for a model and update its status."""
        spec = self.get_model(model_id)
        if not spec:
            return ModelStatus.NOT_INSTALLED, [f"Model '{model_id}' is not registered."]

        models_dir = self._settings_service.get_settings().models_dir
        self._registry.refresh_statuses(models_dir)

        is_valid, problems = self.validate_model(model_id)
        return spec.status, problems

    def rescan_all(self) -> None:
        """Re-scan all registered models against disk files."""
        models_dir = self._settings_service.get_settings().models_dir
        self._registry.refresh_statuses(models_dir)

        for spec in self._registry.list_all():
            model_path = self._store.model_path_for_spec(spec)
            if model_path.exists() and any(model_path.iterdir()):
                self.validate_model(spec.model_id)

        logger.info("Re-scanned all local models.")
        self.registry_refreshed.emit()

    def select_active_model(self, model_id: str) -> bool:
        """Set active generation target model."""
        spec = self.get_model(model_id)
        if not spec:
            logger.warning("Cannot select unregistered model '%s'.", model_id)
            return False

        current_settings = self._settings_service.get_settings()
        current_settings.default_model_id = model_id
        errors = self._settings_service.save_settings(current_settings)

        if errors:
            logger.error("Failed to set active model '%s': %s", model_id, errors)
            return False

        logger.info("Selected model '%s' as active generation target.", model_id)
        self.model_updated.emit(spec)
        return True

    def register_custom_model(self, model_dir: str | Path) -> Tuple[Optional[ModelSpec], List[str]]:
        """Discover, validate, and register a local custom model."""
        spec, errors = detect_and_validate_custom_model(model_dir)
        if errors or spec is None:
            return None, errors

        spec.status = ModelStatus.READY
        try:
            self._registry.register(spec)
            self.save_custom_models()
            logger.info("Registered custom model '%s' from %s", spec.model_id, model_dir)
            self.model_updated.emit(spec)
            return spec, []
        except Exception as exc:
            logger.exception("Failed to register custom model spec: %s", exc)
            return None, [f"Registration error: {exc}"]

    def remove_model(self, model_id: str, delete_files: bool = False) -> Tuple[bool, str]:
        """Remove model from registry, with optional explicit file deletion."""
        spec = self.get_model(model_id)
        if not spec:
            return False, f"Model '{model_id}' not found in registry."

        model_path = self._store.model_path_for_spec(spec)

        # 1. Unregister from in-memory registry
        if model_id in self._registry._specs:
            del self._registry._specs[model_id]

        # 2. Persist custom models list
        if spec.is_custom:
            self.save_custom_models()

        # 3. Explicit file deletion if requested
        if delete_files:
            try:
                if model_path.exists():
                    shutil.rmtree(model_path)
                    logger.info("Permanently deleted model files for '%s' from disk (%s)", model_id, model_path)
            except Exception as exc:
                logger.exception("Failed to delete model directory %s: %s", model_path, exc)
                return False, f"Removed from registry, but failed to delete files from disk: {exc}"

        # 4. Handle active model reset if active model was removed
        current_active = self._settings_service.get_settings().default_model_id
        if current_active == model_id:
            remaining = self.get_all_models()
            if remaining:
                self.select_active_model(remaining[0].model_id)

        logger.info("Removed model '%s' from NOVA registry (delete_files=%s).", model_id, delete_files)
        self.model_removed.emit(model_id)
        return True, f"Successfully removed '{spec.display_name}' from NOVA catalog."

    # ---------------------------------------------------------------------- #
    # Custom Spec Persistence Helpers                                          #
    # ---------------------------------------------------------------------- #

    def save_custom_models(self) -> None:
        """Save registered custom model specs to custom_specs.json in models_dir."""
        models_dir = Path(self._settings_service.get_settings().models_dir)
        models_dir.mkdir(parents=True, exist_ok=True)

        target_file = models_dir / "custom_specs.json"
        custom_specs = [s for s in self._registry.list_all() if s.is_custom]

        data_list = []
        for spec in custom_specs:
            data_list.append({
                "model_id": spec.model_id,
                "display_name": spec.display_name,
                "description": spec.description,
                "source": spec.source,
                "architecture": spec.architecture,
                "runtime": spec.runtime,
                "license": spec.license,
                "min_vram_gb": spec.min_vram_gb,
                "recommended_vram_gb": spec.recommended_vram_gb,
                "model_size_gb": spec.model_size_gb,
                "precision": spec.precision,
                "capabilities": spec.capabilities,
                "is_custom": True,
            })

        temp_file = target_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data_list, f, indent=2)
            os.replace(temp_file, target_file)
            logger.info("Saved %d custom model specs to %s", len(custom_specs), target_file)
        except Exception as exc:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            logger.warning("Failed to save custom model specs to %s: %s", target_file, exc)

    def load_persisted_custom_models(self, models_dir: str | Path) -> int:
        """Load custom model specs from custom_specs.json in models_dir."""
        target_file = Path(models_dir) / "custom_specs.json"
        if not target_file.exists():
            return 0

        loaded_count = 0
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data_list = json.load(f)

            if isinstance(data_list, list):
                for d in data_list:
                    if isinstance(d, dict) and "model_id" in d:
                        spec = ModelSpec(
                            model_id=d["model_id"],
                            display_name=d.get("display_name", d["model_id"]),
                            description=d.get("description", ""),
                            source=d.get("source", ""),
                            architecture=d.get("architecture", "custom"),
                            runtime=d.get("runtime", "diffusers_flux"),
                            license=d.get("license", "Custom / Local"),
                            min_vram_gb=d.get("min_vram_gb", 8.0),
                            recommended_vram_gb=d.get("recommended_vram_gb", 12.0),
                            model_size_gb=d.get("model_size_gb", 0.0),
                            precision=d.get("precision", "fp16"),
                            capabilities=d.get("capabilities", ["text-to-image"]),
                            is_custom=True,
                            status=ModelStatus.INSTALLED,
                        )
                        self._registry.register(spec)
                        loaded_count += 1

            logger.info("Loaded %d persisted custom model specs from %s", loaded_count, target_file)
        except Exception as exc:
            logger.warning("Failed to load custom specs from %s: %s", target_file, exc)

        return loaded_count

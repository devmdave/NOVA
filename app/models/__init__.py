"""
Models package — public re-exports.
"""
from .errors import (
    ModelError,
    ModelLoadError,
    ModelNotFoundError,
    ModelNotInstalledError,
    ModelValidationError,
    RuntimeNotAvailableError,
    SpecValidationError,
)
from .registry import ModelRegistry
from .spec import ModelSpec, ModelStatus
from .store import LocalModelStore
from .service import ModelService
from .catalog import get_official_catalog, get_catalog_item
from .acquisition import ModelAcquisitionService
from .hf_utils import parse_hf_repo_id, inspect_hf_custom_model

__all__ = [
    # Spec & status
    "ModelSpec",
    "ModelStatus",
    # Registry
    "ModelRegistry",
    # Store
    "LocalModelStore",
    # Service
    "ModelService",
    # Acquisition & Catalog
    "ModelAcquisitionService",
    "get_official_catalog",
    "get_catalog_item",
    "parse_hf_repo_id",
    "inspect_hf_custom_model",
    # Errors
    "ModelError",
    "ModelNotFoundError",
    "ModelNotInstalledError",
    "ModelValidationError",
    "ModelLoadError",
    "RuntimeNotAvailableError",
    "SpecValidationError",
]

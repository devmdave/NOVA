"""
HistoryService — application core service for managing generation history.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from app.history.models import GenerationRecord
from app.history.repository import HistoryRepository
from app.inference.models import GenerationResult

logger = logging.getLogger("nova.history.service")


class HistoryService(QObject):
    """Core service for managing history records and notifications."""

    record_added = Signal(GenerationRecord)
    record_deleted = Signal(str)
    history_cleared = Signal()

    def __init__(self, repository: HistoryRepository) -> None:
        super().__init__()
        self._repository = repository

    @property
    def repository(self) -> HistoryRepository:
        return self._repository

    def save_generation(
        self, result: GenerationResult, model_id: str = "flux-schnell"
    ) -> Optional[GenerationRecord]:
        """Convert a successful GenerationResult into a persistent record."""
        if not result.success:
            logger.debug("Skipping history save for un-successful generation result.")
            return None

        image_bytes: Optional[bytes] = result.image_data

        if not image_bytes and result.image_path:
            try:
                with open(result.image_path, "rb") as f:
                    image_bytes = f.read()
            except Exception as exc:
                logger.error("Failed to read image bytes from path %s: %s", result.image_path, exc)
                return None

        if not image_bytes:
            logger.error("No image data or file path available in GenerationResult to save history.")
            return None

        effective_seed = result.seed_used if result.seed_used != -1 else result.request.seed

        record = GenerationRecord(
            id="",  # Repository will generate ID if empty
            image_path="",
            thumbnail_path="",
            prompt=result.request.prompt,
            negative_prompt=result.request.negative_prompt or "",
            width=result.request.width,
            height=result.request.height,
            steps=result.request.steps,
            guidance=result.request.guidance,
            seed=effective_seed,
            model=result.metadata.get("model", model_id or "flux-schnell"),
            mode=result.request.mode,
            denoising_strength=result.request.denoising_strength,
            duration_seconds=result.duration_seconds,
            metadata=result.metadata or {},
        )

        try:
            saved_record = self._repository.save(record, image_bytes)
            logger.info("Saved generation history record %s", saved_record.id)
            self.record_added.emit(saved_record)
            return saved_record
        except Exception as exc:
            logger.exception("Failed to save history record: %s", exc)
            return None

    def get_history(self) -> List[GenerationRecord]:
        """Fetch all generation history records (newest first)."""
        return self._repository.get_all()

    def delete_record(self, record_id: str) -> bool:
        """Delete a record by ID."""
        success = self._repository.delete(record_id)
        if success:
            logger.info("Deleted history record %s", record_id)
            self.record_deleted.emit(record_id)
        return success

    def clear_history(self) -> int:
        """Clear all generation records."""
        count = self._repository.clear()
        if count > 0:
            logger.info("Cleared %d history records", count)
            self.history_cleared.emit()
        return count

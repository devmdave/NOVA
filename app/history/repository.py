"""
History repository layer — handles persistent local storage of history metadata and images.
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QBuffer, QIODevice, QByteArray
from PySide6.QtGui import QImage

from app.history.models import GenerationRecord

logger = logging.getLogger("nova.history.repository")


class HistoryRepository(ABC):
    """Abstract interface for storing and retrieving history records."""

    @abstractmethod
    def save(self, record: GenerationRecord, image_bytes: bytes) -> GenerationRecord:
        """Save a new generation record and image. Returns the persisted record."""

    @abstractmethod
    def get_all(self) -> List[GenerationRecord]:
        """Return all valid generation records, newest first."""

    @abstractmethod
    def get_by_id(self, record_id: str) -> Optional[GenerationRecord]:
        """Return a single record by ID, or None if not found/invalid."""

    @abstractmethod
    def delete(self, record_id: str) -> bool:
        """Delete a single generation record and associated image assets."""

    @abstractmethod
    def clear(self) -> int:
        """Delete all history records and assets. Returns count of deleted records."""


class LocalHistoryRepository(HistoryRepository):
    """File-system based implementation of HistoryRepository.

    Directory structure:
        <storage_dir>/
          ├── records/
          │     └── <id>.json
          ├── images/
          │     └── <id>.png
          └── thumbnails/
                └── <id>.png
    """

    THUMBNAIL_MAX_DIM = 256

    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = Path(storage_dir).expanduser().resolve()
        self.records_dir = self.storage_dir / "records"
        self.images_dir = self.storage_dir / "images"
        self.thumbnails_dir = self.storage_dir / "thumbnails"

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create storage directory tree if it does not exist."""
        for path in (self.storage_dir, self.records_dir, self.images_dir, self.thumbnails_dir):
            path.mkdir(parents=True, exist_ok=True)

    def save(self, record: GenerationRecord, image_bytes: bytes) -> GenerationRecord:
        """Save a generation record and image file atomically."""
        if not image_bytes:
            raise ValueError("Cannot save history record with empty image bytes.")

        if not record.id:
            timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:19]
            record.id = f"gen_{timestamp_str}"

        self._ensure_directories()

        img_path = self.images_dir / f"{record.id}.png"
        thumb_path = self.thumbnails_dir / f"{record.id}.png"
        meta_path = self.records_dir / f"{record.id}.json"

        # 1. Save full resolution image safely
        try:
            self._write_bytes_atomic(img_path, image_bytes)
        except Exception as exc:
            logger.exception("Failed to write image file for record %s", record.id)
            raise IOError(f"Failed to write image file: {exc}") from exc

        # 2. Save thumbnail
        try:
            thumb_bytes = self._create_thumbnail(image_bytes)
            self._write_bytes_atomic(thumb_path, thumb_bytes)
        except Exception as exc:
            logger.warning("Failed to create thumbnail for record %s, reusing original image: %s", record.id, exc)
            shutil.copyfile(img_path, thumb_path)

        # 3. Save metadata JSON
        record.image_path = str(img_path)
        record.thumbnail_path = str(thumb_path)

        try:
            meta_json = json.dumps(record.to_dict(), indent=2)
            self._write_bytes_atomic(meta_path, meta_json.encode("utf-8"))
        except Exception as exc:
            logger.exception("Failed to write metadata for record %s", record.id)
            # Cleanup created image files on metadata failure
            img_path.unlink(missing_ok=True)
            thumb_path.unlink(missing_ok=True)
            raise IOError(f"Failed to write metadata file: {exc}") from exc

        logger.info("Saved history record %s to %s", record.id, meta_path)
        return record

    def get_all(self) -> List[GenerationRecord]:
        """Load all generation records, ignoring missing or corrupted items."""
        self._ensure_directories()
        records: List[GenerationRecord] = []

        for json_path in self.records_dir.glob("*.json"):
            record = self._load_record_file(json_path)
            if record is not None:
                records.append(record)

        # Sort newest first by timestamp (fallback to id if timestamp missing)
        records.sort(key=lambda r: r.timestamp or r.id, reverse=True)
        return records

    def get_by_id(self, record_id: str) -> Optional[GenerationRecord]:
        """Fetch record by ID."""
        json_path = self.records_dir / f"{record_id}.json"
        if not json_path.exists():
            return None
        return self._load_record_file(json_path)

    def delete(self, record_id: str) -> bool:
        """Safely delete record metadata, image, and thumbnail."""
        self._ensure_directories()
        meta_path = self.records_dir / f"{record_id}.json"
        img_path = self.images_dir / f"{record_id}.png"
        thumb_path = self.thumbnails_dir / f"{record_id}.png"

        deleted_any = False

        for path in (meta_path, img_path, thumb_path):
            try:
                if path.exists():
                    path.unlink()
                    deleted_any = True
            except Exception as exc:
                logger.warning("Error deleting file %s: %s", path, exc)

        return deleted_any

    def clear(self) -> int:
        """Delete all history records and images."""
        all_records = self.get_all()
        count = 0
        for rec in all_records:
            if self.delete(rec.id):
                count += 1
        return count

    # ---------------------------------------------------------------------- #
    # Internal Helpers                                                         #
    # ---------------------------------------------------------------------- #

    def _load_record_file(self, json_path: Path) -> Optional[GenerationRecord]:
        """Safely load and validate a record JSON file."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not isinstance(data, dict):
                logger.warning("Corrupted metadata in %s: not a JSON object", json_path)
                return None

            record = GenerationRecord.from_dict(data)

            # Validate that referenced image file actually exists
            if not record.image_path or not os.path.exists(record.image_path):
                logger.warning(
                    "Missing image file for record %s (%s); skipping",
                    record.id, record.image_path
                )
                return None

            # Fallback if thumbnail missing
            if not record.thumbnail_path or not os.path.exists(record.thumbnail_path):
                record.thumbnail_path = record.image_path

            return record
        except Exception as exc:
            logger.warning("Failed to load history record from %s: %s", json_path, exc)
            return None

    def _create_thumbnail(self, image_bytes: bytes) -> bytes:
        """Create thumbnail PNG bytes from raw image bytes using QImage."""
        qimg = QImage()
        if not qimg.loadFromData(image_bytes):
            # Fallback: return original bytes if image parsing fails
            return image_bytes

        scaled = qimg.scaled(
            self.THUMBNAIL_MAX_DIM,
            self.THUMBNAIL_MAX_DIM,
            aspectRatioMode=1,  # Qt.KeepAspectRatio
            transformMode=1,    # Qt.SmoothTransformation
        )

        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        scaled.save(buf, "PNG")
        buf.close()
        return bytes(ba.data())

    @staticmethod
    def _write_bytes_atomic(target_path: Path, data: bytes) -> None:
        """Write bytes atomically using a temporary file."""
        temp_dir = target_path.parent
        with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False) as tmp_file:
            tmp_file.write(data)
            tmp_path = Path(tmp_file.name)

        os.replace(tmp_path, target_path)

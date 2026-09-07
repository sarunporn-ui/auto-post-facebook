"""Lightweight JSON-file storage layer.

Acts as the project's "database" for the MVP: each entity type is persisted
as a JSON array in its own file under `data/`. Swap this module for a real
database (Postgres/SQLite) once volume requires it — every other module only
depends on the save/get/list/update methods below.
"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Generic, Optional, Type, TypeVar

from pydantic import BaseModel

from src.config import get_settings

T = TypeVar("T", bound=BaseModel)
_lock = threading.Lock()


class JsonStore(Generic[T]):
    def __init__(self, name: str, model: Type[T]):
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.path: Path = settings.data_dir / f"{name}.json"
        self.model = model
        if not self.path.exists():
            self.path.write_text("[]")

    def _read(self) -> list[dict]:
        with _lock:
            if not self.path.exists():
                return []
            return json.loads(self.path.read_text() or "[]")

    def _write(self, items: list[dict]) -> None:
        with _lock:
            self.path.write_text(json.dumps(items, indent=2, ensure_ascii=False))

    def save(self, item: T) -> T:
        items = self._read()
        items.append(json.loads(item.model_dump_json()))
        self._write(items)
        return item

    def get(self, item_id: str) -> Optional[T]:
        for raw in self._read():
            if raw.get("id") == item_id:
                return self.model.model_validate(raw)
        return None

    def list(self) -> list[T]:
        return [self.model.model_validate(raw) for raw in self._read()]

    def update(self, item: T) -> T:
        items = self._read()
        updated = json.loads(item.model_dump_json())
        for i, raw in enumerate(items):
            if raw.get("id") == item.id:
                items[i] = updated
                break
        else:
            items.append(updated)
        self._write(items)
        return item

"""History storage. DynamoDB when DDB_TABLE is set (AWS), otherwise a small in-memory ring buffer."""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Protocol

from app.config import get_settings


class Store(Protocol):
    kind: str

    def save(self, item: dict) -> str: ...
    def recent(self, limit: int = 10) -> list[dict]: ...


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class MemoryStore:
    kind = "memory"

    def __init__(self, maxlen: int = 50):
        self._items: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def save(self, item: dict) -> str:
        item = {**item, "created_at": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            self._items.appendleft(item)
        return item["id"]

    def recent(self, limit: int = 10) -> list[dict]:
        with self._lock:
            return list(self._items)[:limit]


class DynamoStore:
    kind = "dynamodb"

    def __init__(self, table_name: str, region: str, ttl_days: int):
        import boto3  # lazy import: not needed locally

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._ttl_days = ttl_days

    def save(self, item: dict) -> str:
        now = datetime.now(timezone.utc)
        self._table.put_item(Item={
            **item,
            "created_at": now.isoformat(),
            "expires_at": int(time.time()) + self._ttl_days * 86400,  # DynamoDB TTL attribute
        })
        return item["id"]

    def recent(self, limit: int = 10) -> list[dict]:
        # A Scan is fine for a demo-sized table; a production table would use a GSI on created_at.
        items = self._table.scan(Limit=100).get("Items", [])
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items[:limit]


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        s = get_settings()
        _store = DynamoStore(s.ddb_table, s.region, s.history_ttl_days) if s.ddb_table else MemoryStore()
    return _store


def reset_store() -> None:  # used by tests
    global _store
    _store = None

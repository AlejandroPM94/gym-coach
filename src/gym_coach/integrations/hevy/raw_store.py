import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class RawResponseStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, resource: str, payload: Any) -> Path:
        target_dir = self._root / resource
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        target = target_dir / f"{timestamp}_{uuid4().hex}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

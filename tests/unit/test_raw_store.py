import json
from pathlib import Path

from gym_coach.integrations.hevy.raw_store import RawResponseStore


def test_saves_raw_payload(tmp_path: Path) -> None:
    payload = {"user": {"id": "1"}}
    target = RawResponseStore(tmp_path).save("user", payload)
    assert target.parent == tmp_path / "user"
    assert json.loads(target.read_text(encoding="utf-8")) == payload

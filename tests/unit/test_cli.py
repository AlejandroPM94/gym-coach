import sys
from pathlib import Path

import httpx
import pytest
import respx

from gym_coach import cli
from gym_coach.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        HEVY_API_KEY="non-secret-test-placeholder",
        GYM_COACH_HEVY_BASE_URL="https://hevy.test",
        GYM_COACH_RAW_DATA_DIR=tmp_path,
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("check", "Connection to Hevy succeeded."),
        ("user", "Downloaded Hevy user information."),
    ],
)
@respx.mock
def test_user_commands(
    command: str,
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": "anonymous-user-id",
                    "name": "Private Test Name",
                    "url": None,
                    "extra": True,
                }
            },
        )
    )
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(sys, "argv", ["gym-coach", "hevy", command])

    cli.main()

    output = capsys.readouterr()
    assert output.out.strip() == expected
    assert output.err == ""
    assert "Private Test Name" not in output.out

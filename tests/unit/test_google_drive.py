from pathlib import Path

import httpx
import pytest
import respx

from gym_coach.integrations.google_drive import client as drive_module
from gym_coach.integrations.google_drive.client import DriveClient, DriveError


class _Credentials:
    valid = True
    token = "private-test-token"

    def refresh(self, _: object) -> None:
        raise AssertionError("valid credentials must not refresh")


@pytest.mark.asyncio
@respx.mock
async def test_drive_lists_exact_folder_and_downloads_declared_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        drive_module.Credentials,
        "from_service_account_file",
        lambda *args, **kwargs: _Credentials(),
    )
    listing = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "abcdefghijk",
                        "name": "Health Connect.zip",
                        "modifiedTime": "2026-09-15T08:00:00Z",
                        "size": "4",
                        "md5Checksum": "098f6bcd4621d373cade4e832627b4f6",
                    }
                ]
            },
        )
    )
    download = respx.get("https://www.googleapis.com/drive/v3/files/abcdefghijk").mock(
        return_value=httpx.Response(200, content=b"test")
    )
    async with DriveClient(tmp_path / "credentials.json", "folder_id_12345") as client:
        file = await client.latest_export()
        assert file is not None
        destination = tmp_path / "export.zip"
        await client.download(file, destination)
    assert destination.read_bytes() == b"test"
    assert listing.called and download.called
    assert "'folder_id_12345' in parents" in listing.calls[0].request.url.params["q"]
    assert listing.calls[0].request.url.params["q"].endswith("name = 'Health Connect.zip'")
    assert download.calls[0].request.headers["Authorization"] == "Bearer private-test-token"


@pytest.mark.asyncio
@respx.mock
async def test_drive_errors_are_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        drive_module.Credentials,
        "from_service_account_file",
        lambda *args, **kwargs: _Credentials(),
    )
    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(403, json={"error": {"message": "private remote detail"}})
    )
    async with DriveClient(tmp_path / "credentials.json", "folder_id_12345") as client:
        with pytest.raises(DriveError, match="HTTP 403") as captured:
            await client.latest_export()
    assert "private remote detail" not in str(captured.value)

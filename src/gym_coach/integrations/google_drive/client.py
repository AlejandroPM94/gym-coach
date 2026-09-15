import asyncio
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_API = "https://www.googleapis.com/drive/v3"
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024


class DriveError(RuntimeError):
    """Sanitized Google Drive boundary error."""


class DriveFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{10,200}$")
    name: str
    modifiedTime: AwareDatetime
    size: int = Field(ge=0, le=MAX_DOWNLOAD_BYTES)
    md5Checksum: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{32}$")

    @property
    def modified_at(self) -> datetime:
        return self.modifiedTime

    @property
    def revision_key(self) -> str:
        return self.md5Checksum or f"{self.modifiedTime.isoformat()}:{self.size}"


class DriveClient:
    def __init__(
        self,
        service_account_file: Path,
        folder_id: str,
        *,
        filename: str = "Health Connect.zip",
        timeout_seconds: float = 30,
    ) -> None:
        if not IDENTIFIER_PATTERN.fullmatch(folder_id):
            raise DriveError("Google Drive health folder ID is invalid")
        if (
            not filename
            or len(filename) > 255
            or any(character in filename for character in "\r\n")
        ):
            raise DriveError("Google Drive health filename is invalid")
        try:
            self._credentials = Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
                service_account_file,
                scopes=[DRIVE_READONLY_SCOPE],
            )
        except (OSError, ValueError) as exc:
            raise DriveError("Google Drive service account could not be loaded") from exc
        self._folder_id = folder_id
        self._filename = filename
        self._client = httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False)
        self._auth_lock = asyncio.Lock()

    async def __aenter__(self) -> "DriveClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()

    async def latest_export(self) -> DriveFile | None:
        escaped_name = self._filename.replace("\\", "\\\\").replace("'", "\\'")
        query = f"'{self._folder_id}' in parents and trashed = false and name = '{escaped_name}'"
        payload = await self._request_json(
            "GET",
            f"{DRIVE_API}/files",
            params={
                "q": query,
                "spaces": "drive",
                "orderBy": "modifiedTime desc",
                "pageSize": "2",
                "fields": "files(id,name,modifiedTime,size,md5Checksum)",
            },
        )
        files = payload.get("files")
        if not isinstance(files, list):
            raise DriveError("Google Drive returned an invalid file list")
        try:
            parsed = [DriveFile.model_validate(item) for item in files]
        except ValueError as exc:
            raise DriveError("Google Drive returned invalid file metadata") from exc
        if len(parsed) > 1 and parsed[0].modified_at == parsed[1].modified_at:
            raise DriveError("Multiple current Health Connect exports are ambiguous")
        return parsed[0] if parsed else None

    async def download(self, file: DriveFile, destination: Path) -> None:
        headers = await self._authorization_headers()
        try:
            async with self._client.stream(
                "GET",
                f"{DRIVE_API}/files/{file.id}",
                params={"alt": "media"},
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    raise DriveError(
                        f"Google Drive download failed with HTTP {response.status_code}"
                    )
                received = 0
                checksum = hashlib.md5(usedforsecurity=False)
                with destination.open("wb") as stream:
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > MAX_DOWNLOAD_BYTES or received > file.size + 1024:
                            raise DriveError("Google Drive export exceeds its declared size")
                        checksum.update(chunk)
                        stream.write(chunk)
                if received != file.size:
                    raise DriveError("Google Drive export size did not match metadata")
                if (
                    file.md5Checksum is not None
                    and checksum.hexdigest() != file.md5Checksum.lower()
                ):
                    raise DriveError("Google Drive export checksum did not match metadata")
        except httpx.HTTPError as exc:
            raise DriveError("Google Drive download failed") from exc

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str],
    ) -> dict[str, Any]:
        headers = await self._authorization_headers()
        try:
            response = await self._client.request(method, url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise DriveError("Google Drive request failed") from exc
        if response.status_code != 200:
            raise DriveError(f"Google Drive request failed with HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise DriveError("Google Drive returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise DriveError("Google Drive returned invalid JSON")
        return payload

    async def _authorization_headers(self) -> dict[str, str]:
        async with self._auth_lock:
            try:
                if not self._credentials.valid:
                    await asyncio.to_thread(self._credentials.refresh, Request())
            except Exception as exc:
                raise DriveError("Google Drive authentication failed") from exc
            token = self._credentials.token
            if not token:
                raise DriveError("Google Drive authentication returned no token")
            return {"Authorization": f"Bearer {token}"}

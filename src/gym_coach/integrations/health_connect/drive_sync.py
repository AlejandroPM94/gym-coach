from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.integrations.google_drive.client import DriveClient, DriveFile
from gym_coach.integrations.health_connect.export import parse_health_connect_export
from gym_coach.integrations.health_connect.service import HealthConnectService
from gym_coach.persistence.models import TrackingRecord

IMPORT_CONTRACT_VERSION = 3


class DriveReader(Protocol):
    async def latest_export(self) -> DriveFile | None: ...

    async def download(self, file: DriveFile, destination: Path) -> None: ...


class HealthDriveSyncResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["imported", "unchanged", "not_found"]
    accepted_days: int = 0
    accepted_body_measurements: int = 0
    modified_at: str | None = None


class HealthDriveSyncService:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        drive: DriveReader,
        *,
        timezone: str,
    ) -> None:
        self._factory = factory
        self._drive = drive
        self._timezone = timezone
        self._storage = HealthConnectService(factory)

    async def sync(self) -> HealthDriveSyncResult:
        file = await self._drive.latest_export()
        if file is None:
            return HealthDriveSyncResult(status="not_found")
        request_id = uuid5(
            NAMESPACE_URL,
            f"gym-coach:health-drive:v{IMPORT_CONTRACT_VERSION}:{file.id}:{file.revision_key}",
        )
        async with self._factory() as session:
            existing = await session.scalar(
                select(TrackingRecord.id).where(TrackingRecord.id == request_id)
            )
        if existing is not None:
            return HealthDriveSyncResult(
                status="unchanged",
                modified_at=file.modified_at.isoformat(),
            )
        with TemporaryDirectory(prefix="gym-coach-drive-") as directory:
            archive = Path(directory) / "Health Connect.zip"
            await self._drive.download(file, archive)
            batch = parse_health_connect_export(
                archive,
                request_id=request_id,
                observed_at=file.modified_at,
                timezone=self._timezone,
            )
            result = await self._storage.ingest(batch)
        return HealthDriveSyncResult(
            status="imported",
            accepted_days=result.accepted_days,
            accepted_body_measurements=result.accepted_body_measurements,
            modified_at=file.modified_at.isoformat(),
        )


def build_drive_client(
    service_account_file: Path,
    folder_id: str,
    filename: str,
) -> DriveClient:
    return DriveClient(service_account_file, folder_id, filename=filename)

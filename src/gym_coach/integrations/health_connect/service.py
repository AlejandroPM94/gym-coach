from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.nutrition.schemas import NutritionModel
from gym_coach.persistence.models import HealthBodyMeasurement, HealthDaily, TrackingRecord
from gym_coach.tracking.activity import ActivityDay
from gym_coach.tracking.body import BodyMeasurementObservation


class HealthBatch(NutritionModel):
    request_id: UUID
    consent_confirmed: bool
    days: list[ActivityDay] = Field(default_factory=list, max_length=30)
    body_measurements: list[BodyMeasurementObservation] = Field(default_factory=list, max_length=90)

    @model_validator(mode="after")
    def valid_records(self) -> "HealthBatch":
        if not self.days and not self.body_measurements:
            raise ValueError("At least one health record is required")
        keys = {(d.day, d.timezone, d.source) for d in self.days}
        if len(keys) != len(self.days):
            raise ValueError("Duplicate daily keys in batch")
        measurement_keys = {(m.source, m.external_id) for m in self.body_measurements}
        if len(measurement_keys) != len(self.body_measurements):
            raise ValueError("Duplicate body measurement keys in batch")
        return self


class HealthImportResult(NutritionModel):
    request_id: UUID
    accepted_days: int
    accepted_body_measurements: int


class HealthImportError(ValueError):
    """Sanitized import boundary error."""


class HealthConnectService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def ingest(self, batch: HealthBatch) -> HealthImportResult:
        if batch.consent_confirmed is not True:
            raise HealthImportError("Enable and confirm health synchronization on the phone first")
        if any(d.observed_at > datetime.now(UTC) + timedelta(minutes=5) for d in batch.days):
            raise HealthImportError("Observation timestamp is in the future")
        if any(
            m.observed_at > datetime.now(UTC) + timedelta(minutes=5)
            for m in batch.body_measurements
        ):
            raise HealthImportError("Observation timestamp is in the future")
        payload = batch.model_dump(mode="json")
        record_day = min(
            [d.day for d in batch.days]
            + [measurement.measured_on for measurement in batch.body_measurements]
        )
        async with self.factory.begin() as session:
            await session.execute(
                insert(TrackingRecord)
                .values(
                    id=batch.request_id,
                    kind="health_import",
                    day=record_day,
                    payload=payload,
                    user_confirmed=True,
                )
                .on_conflict_do_nothing(index_elements=[TrackingRecord.id])
            )
            audit = await session.scalar(
                select(TrackingRecord).where(TrackingRecord.id == batch.request_id)
            )
            assert audit is not None
            if audit.kind != "health_import" or audit.payload != payload:
                raise HealthImportError("Request ID already used with different data")
            for day in batch.days:
                values = day.model_dump()
                values["exercise_minutes_by_type"] = day.model_dump(mode="json")[
                    "exercise_minutes_by_type"
                ]
                statement = insert(HealthDaily).values(**values)
                update_fields = {
                    name: getattr(statement.excluded, name)
                    for name in ActivityDay.model_fields
                    if name not in {"day", "timezone", "source"}
                }
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[HealthDaily.day, HealthDaily.timezone, HealthDaily.source],
                        set_=update_fields,
                        where=HealthDaily.observed_at <= statement.excluded.observed_at,
                    )
                )
            for measurement in batch.body_measurements:
                statement = insert(HealthBodyMeasurement).values(**measurement.model_dump())
                update_fields = {
                    name: getattr(statement.excluded, name)
                    for name in BodyMeasurementObservation.model_fields
                    if name not in {"source", "external_id"}
                }
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[
                            HealthBodyMeasurement.source,
                            HealthBodyMeasurement.external_id,
                        ],
                        set_=update_fields,
                        where=(HealthBodyMeasurement.observed_at <= statement.excluded.observed_at),
                    )
                )
        return HealthImportResult(
            request_id=batch.request_id,
            accepted_days=len(batch.days),
            accepted_body_measurements=len(batch.body_measurements),
        )

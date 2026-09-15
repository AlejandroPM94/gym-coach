from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.coaching.assessment import calculate_mifflin_st_jeor
from gym_coach.mcp.schemas import AthleteCheckInView, AthleteMeasurementView
from gym_coach.metrics.service import MetricsService
from gym_coach.nutrition.calculations import scale, total
from gym_coach.nutrition.service import NutritionService
from gym_coach.persistence.models import (
    AthleteCheckIn,
    AthleteMeasurement,
    AthleteProfile,
    HealthBodyMeasurement,
    HealthDaily,
    TrackingRecord,
    TrainingGoal,
)
from gym_coach.tracking.activity import ActivityDay, ActivitySummary, assess_recovery
from gym_coach.tracking.body import BodyMeasurementObservation, body_measurement_trends
from gym_coach.tracking.calculations import (
    calculate_target,
    difference,
    fingerprint,
    measurement_trends,
    rounded,
)
from gym_coach.tracking.schemas import (
    DayClosure,
    NutritionDayReview,
    NutritionDifference,
    TargetParameters,
    TargetPreview,
    TargetVersion,
    WeeklyReview,
)


class TrackingService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.nutrition = NutritionService(factory)

    async def _store(
        self, request_id: UUID, kind: str, day: date, payload: dict[str, object], confirmed: bool
    ) -> TrackingRecord:
        if confirmed is not True:
            raise ValueError("Explicit confirmation is required")
        async with self.factory.begin() as session:
            await session.execute(
                insert(TrackingRecord)
                .values(id=request_id, kind=kind, day=day, payload=payload, user_confirmed=True)
                .on_conflict_do_nothing(index_elements=[TrackingRecord.id])
            )
            row = await session.scalar(
                select(TrackingRecord).where(TrackingRecord.id == request_id)
            )
            assert row is not None
            if row.kind != kind or row.payload != payload or row.day != day:
                raise ValueError("Request ID already used with different data")
            return row

    async def preview_target(self, parameters: TargetParameters) -> TargetPreview:
        today = date.today()
        async with self.factory() as session:
            profile = await session.scalar(
                select(AthleteProfile).where(AthleteProfile.profile_key == "default")
            )
            if (
                profile is None
                or not profile.health_reviewed
                or not profile.nutrition_reviewed
                or not profile.lifestyle_reviewed
            ):
                raise ValueError(
                    "Complete and confirm health, nutrition and lifestyle interview first"
                )
            if profile.health_conditions or profile.medications_affecting_training:
                raise ValueError(
                    "Clinical conditions require professional review; automatic targets unavailable"
                )
            if profile.birth_year is None or not 19 <= today.year - profile.birth_year <= 100:
                raise ValueError("Adult age must be established from the confirmed birth year")
            manual_weight = await session.scalar(
                select(AthleteMeasurement)
                .where(
                    AthleteMeasurement.profile_id == profile.id,
                    AthleteMeasurement.weight_kg.is_not(None),
                    AthleteMeasurement.measured_on <= today,
                )
                .order_by(AthleteMeasurement.measured_on.desc())
            )
            wearable_weight = await session.scalar(
                select(HealthBodyMeasurement)
                .where(
                    HealthBodyMeasurement.weight_kg.is_not(None),
                    HealthBodyMeasurement.measured_on <= today,
                )
                .order_by(
                    HealthBodyMeasurement.measured_on.desc(),
                    HealthBodyMeasurement.measured_at.asc(),
                )
            )
            use_wearable = wearable_weight is not None and (
                manual_weight is None or wearable_weight.measured_on > manual_weight.measured_on
            )
            weight_kg = (
                wearable_weight.weight_kg
                if use_wearable and wearable_weight is not None
                else manual_weight.weight_kg
                if manual_weight is not None
                else None
            )
            weight_measured_on = (
                wearable_weight.measured_on
                if use_wearable and wearable_weight is not None
                else manual_weight.measured_on
                if manual_weight is not None
                else None
            )
            if (
                weight_kg is None
                or weight_measured_on is None
                or (today - weight_measured_on).days > 30
                or profile.height_cm is None
            ):
                raise ValueError("Height and a weight from the last 30 days are required")
            resting = calculate_mifflin_st_jeor(
                weight_kg=weight_kg,
                height_cm=profile.height_cm,
                age=today.year - profile.birth_year,
                sex=profile.sex_for_energy_equation or "unspecified",
            )
            if resting is None:
                raise ValueError("Energy equation is unavailable for this profile")
            goals = list(
                await session.scalars(
                    select(TrainingGoal.id)
                    .where(TrainingGoal.profile_id == profile.id, TrainingGoal.status == "active")
                    .order_by(TrainingGoal.id)
                )
            )
            if not goals:
                raise ValueError("Confirm a goal before defining nutrition targets")
            maintenance, daily = calculate_target(resting, weight_kg, parameters)
            data = dict(
                parameters=parameters,
                goal_ids=goals,
                profile_version=profile.version,
                weight_measured_on=weight_measured_on,
                weight_kg=weight_kg,
                resting_energy_kcal=resting,
                estimated_maintenance_kcal=maintenance,
                daily=daily,
                fingerprint="",
                limitations=[
                    "Maintenance and activity factor are estimates, not measured expenditure.",
                    "Parameter choices require an explicit rationale and athlete confirmation.",
                    "No wearable calories are added to the activity estimate.",
                    (
                        "Weight comes from an automated openScale measurement."
                        if use_wearable
                        else "Weight comes from a confirmed manual measurement."
                    ),
                    "Adult nutrition only; review complete logs and trends before adjusting.",
                ],
            )
            preview = TargetPreview.model_validate(data)
            return preview.model_copy(
                update={"fingerprint": fingerprint(preview.model_dump(mode="json"))}
            )

    async def save_target(
        self, request_id: UUID, preview: TargetPreview, confirmed: bool
    ) -> TargetVersion:
        if confirmed is not True:
            raise ValueError("Explicit confirmation is required")
        # An already completed retry returns the immutable version even if the profile changed.
        async with self.factory() as session:
            existing = await session.scalar(
                select(TrackingRecord).where(TrackingRecord.id == request_id)
            )
        payload = preview.model_dump(mode="json")
        if existing is not None:
            if existing.kind != "target" or existing.payload != payload:
                raise ValueError("Request ID already used with different data")
            return TargetVersion(id=existing.id, **existing.payload)
        current = await self.preview_target(preview.parameters)
        if current != preview:
            raise ValueError("Target preview is stale or modified; preview and confirm again")
        if preview.parameters.effective_from < date.today():
            raise ValueError("New target versions cannot rewrite past days")
        row = await self._store(
            request_id, "target", preview.parameters.effective_from, payload, confirmed
        )
        return TargetVersion(id=row.id, **row.payload)

    async def day_review(self, day: date, timezone: str) -> NutritionDayReview:
        diary = await self.nutrition.daily(day, timezone)
        digest = fingerprint(diary.model_dump(mode="json"))
        async with self.factory() as session:
            targets = await session.scalar(
                select(TrackingRecord)
                .where(TrackingRecord.kind == "target", TrackingRecord.day <= day)
                .order_by(TrackingRecord.day.desc(), TrackingRecord.sequence.desc())
            )
            closures = list(
                await session.scalars(
                    select(TrackingRecord)
                    .where(TrackingRecord.kind == "closure", TrackingRecord.day == day)
                    .order_by(TrackingRecord.sequence.desc())
                )
            )
        closure = next(
            (
                DayClosure.model_validate(r.payload)
                for r in closures
                if r.payload.get("timezone") == timezone
            ),
            None,
        )
        complete = bool(closure and closure.complete and closure.diary_fingerprint == digest)
        target = TargetVersion(id=targets.id, **targets.payload) if targets else None
        return NutritionDayReview(
            day=day,
            logged=diary.totals,
            has_estimates=diary.has_estimates,
            complete=complete,
            diary_fingerprint=digest,
            target=target,
            difference=difference(diary.totals, target.daily) if complete and target else None,
        )

    async def close_day(self, request_id: UUID, closure: DayClosure, confirmed: bool) -> DayClosure:

        if confirmed is not True:
            raise ValueError("Explicit confirmation is required")
        async with self.factory() as session:
            existing = await session.scalar(
                select(TrackingRecord).where(TrackingRecord.id == request_id)
            )
        if existing is not None:
            if existing.kind != "closure" or existing.payload != closure.model_dump(mode="json"):
                raise ValueError("Request ID already used with different data")
            # Returning an old acknowledgement must not re-close a subsequently edited diary.
            return DayClosure.model_validate(existing.payload)
        if closure.day > datetime.now(ZoneInfo(closure.timezone)).date():
            raise ValueError("Cannot close a future day")
        current = await self.day_review(closure.day, closure.timezone)
        if current.diary_fingerprint != closure.diary_fingerprint:
            raise ValueError("Diary changed; review and confirm again")
        await self._store(
            request_id, "closure", closure.day, closure.model_dump(mode="json"), confirmed
        )
        return closure

    async def weekly_review(self, end: date, timezone: str) -> WeeklyReview:
        days = [
            await self.day_review(end - timedelta(days=i), timezone) for i in reversed(range(7))
        ]
        async with self.factory() as session:
            profile_id = await session.scalar(
                select(AthleteProfile.id).where(AthleteProfile.profile_key == "default")
            )
            measurements = (
                list(
                    await session.scalars(
                        select(AthleteMeasurement)
                        .where(
                            AthleteMeasurement.profile_id == profile_id,
                            AthleteMeasurement.measured_on >= end - timedelta(days=13),
                            AthleteMeasurement.measured_on <= end,
                        )
                        .order_by(AthleteMeasurement.measured_on)
                    )
                )
                if profile_id
                else []
            )
            checks = (
                list(
                    await session.scalars(
                        select(AthleteCheckIn)
                        .where(
                            AthleteCheckIn.profile_id == profile_id,
                            AthleteCheckIn.checked_on >= end - timedelta(days=13),
                            AthleteCheckIn.checked_on <= end,
                        )
                        .order_by(AthleteCheckIn.checked_on)
                    )
                )
                if profile_id
                else []
            )
            wearable_rows = list(
                await session.scalars(
                    select(HealthBodyMeasurement)
                    .where(
                        HealthBodyMeasurement.measured_on >= end - timedelta(days=13),
                        HealthBodyMeasurement.measured_on <= end,
                        HealthBodyMeasurement.timezone == timezone,
                    )
                    .order_by(HealthBodyMeasurement.measured_at)
                )
            )
        measurement_views = [
            AthleteMeasurementView(
                measurement_id=r.id,
                **{
                    k: getattr(r, k)
                    for k in (
                        "measured_on",
                        "weight_kg",
                        "waist_cm",
                        "body_fat_percent",
                        "body_fat_method",
                    )
                },
            )
            for r in measurements
        ]
        check_views = [
            AthleteCheckInView(
                check_in_id=r.id,
                **{
                    k: getattr(r, k)
                    for k in (
                        "checked_on",
                        "sleep_quality",
                        "stress_level",
                        "energy_level",
                        "hunger_level",
                        "soreness_level",
                        "training_adherence",
                        "nutrition_adherence",
                        "notes",
                    )
                },
            )
            for r in checks
        ]
        wearable_views = [
            BodyMeasurementObservation.model_validate(
                {k: getattr(row, k) for k in BodyMeasurementObservation.model_fields}
            )
            for row in wearable_rows
        ]
        complete = [d.logged for d in days if d.complete]
        differences = [d.difference for d in days if d.difference is not None]

        def mean_required(values: list[Decimal]) -> Decimal:
            return rounded(sum(values, Decimal(0)) / len(values))

        def mean_optional(values: list[Decimal | None]) -> Decimal | None:
            return (
                mean_required([value for value in values if value is not None])
                if all(value is not None for value in values)
                else None
            )

        mean_difference = (
            NutritionDifference(
                energy_kcal=mean_required([item.energy_kcal for item in differences]),
                protein_g=mean_required([item.protein_g for item in differences]),
                carbohydrate_g=mean_required([item.carbohydrate_g for item in differences]),
                fat_g=mean_required([item.fat_g for item in differences]),
                fiber_g=mean_optional([item.fiber_g for item in differences]),
            )
            if differences
            else None
        )
        actions = []
        if len(complete) < 7:
            actions.append("Complete missing food logs before drawing weekly intake conclusions.")
        if any(c.soreness_level is not None and c.soreness_level >= 4 for c in check_views):
            actions.append(
                "Ask about recorded discomfort before recommending increased training load."
            )
        if sum(c.energy_level is not None and c.energy_level <= 2 for c in check_views) >= 2:
            actions.append(
                "Review repeated low energy together with sleep, intake and training demands."
            )
        trends = measurement_trends(measurement_views, end)
        wearable_trends = body_measurement_trends(wearable_views, end)
        if trends[0].change is None and wearable_trends[0].change is None:
            actions.append("Insufficient repeated weight measurements to compare weekly trends.")
        activity = await self.activity_summary(end, timezone)
        if activity.recovery.status == "possible_strain":
            actions.append(
                "Review repeated wearable recovery deviations together with symptoms and "
                "performance before increasing training load."
            )
        elif activity.recovery.status == "monitor":
            actions.append(
                "Monitor the isolated recovery deviation; do not change the plan from it alone."
            )
        async with self.factory() as session:
            target_sessions = await session.scalar(
                select(AthleteProfile.training_days_per_week).where(
                    AthleteProfile.profile_key == "default"
                )
            )
        training = (
            await MetricsService(self.factory).summary(
                as_of=datetime.combine(end + timedelta(days=1), time.min, ZoneInfo(timezone)),
                window_days=7,
                target_sessions_per_week=Decimal(target_sessions),
            )
            if target_sessions
            else None
        )
        return WeeklyReview(
            activity=activity,
            training=training,
            end_day=end,
            timezone=timezone,
            days=days,
            complete_days=len(complete),
            mean_complete_day_intake=scale(total(complete), Decimal(1) / len(complete))
            if complete
            else None,
            mean_target_difference=mean_difference,
            measurements=measurement_views,
            wearable_measurements=wearable_views,
            wearable_trends=wearable_trends,
            check_ins=check_views,
            trends=trends,
            limitations=[
                "Differences compare intake to each day's target, not measured energy balance.",
                "Weight changes do not identify fat or muscle changes.",
                "Consumer BIA body-fat estimates are secondary trend signals, not exact values.",
                "No targets or routines are changed automatically.",
            ],
            review_actions=actions,
        )

    async def activity_summary(self, end: date, timezone: str) -> ActivitySummary:
        async with self.factory() as session:
            rows = list(
                await session.scalars(
                    select(HealthDaily)
                    .where(
                        HealthDaily.day >= end - timedelta(days=27),
                        HealthDaily.day <= end,
                        HealthDaily.timezone == timezone,
                    )
                    .order_by(HealthDaily.day)
                )
            )
        all_days = [
            ActivityDay.model_validate({k: getattr(r, k) for k in ActivityDay.model_fields})
            for r in rows
        ]
        days = [item for item in all_days if item.day >= end - timedelta(days=6)]
        steps = [
            Decimal(d.steps)
            for d in days
            if d.steps is not None and d.day < d.observed_at.astimezone(ZoneInfo(d.timezone)).date()
        ]
        sleep = [
            d.sleep_session_minutes
            for d in days
            if d.sleep_session_minutes is not None
            and d.day < d.observed_at.astimezone(ZoneInfo(d.timezone)).date()
        ]
        complete_days = [
            d for d in days if d.day < d.observed_at.astimezone(ZoneInfo(d.timezone)).date()
        ]

        def mean(field: str) -> Decimal | None:
            values = [value for d in complete_days if (value := getattr(d, field)) is not None]
            return rounded(sum(values, Decimal(0)) / len(values)) if values else None

        distances = [d.distance_meters for d in complete_days if d.distance_meters is not None]
        vo2_rows = [d for d in days if d.vo2_max_ml_min_kg is not None]
        return ActivitySummary(
            days=days,
            steps_days=len(steps),
            sleep_days=len(sleep),
            mean_steps=rounded(sum(steps, Decimal(0)) / len(steps)) if steps else None,
            mean_sleep_session_minutes=rounded(sum(sleep, Decimal(0)) / len(sleep))
            if sleep
            else None,
            mean_sleep_asleep_minutes=mean("sleep_asleep_minutes"),
            mean_sleep_deep_minutes=mean("sleep_deep_minutes"),
            mean_sleep_rem_minutes=mean("sleep_rem_minutes"),
            mean_exercise_minutes=mean("exercise_minutes"),
            total_distance_meters=rounded(sum(distances, Decimal(0))) if distances else None,
            mean_resting_heart_rate_bpm=mean("resting_heart_rate_bpm"),
            mean_hrv_rmssd_ms=mean("hrv_rmssd_ms"),
            mean_oxygen_saturation_percent=mean("mean_oxygen_saturation_percent"),
            latest_vo2_max_ml_min_kg=(
                max(vo2_rows, key=lambda item: item.day).vo2_max_ml_min_kg if vo2_rows else None
            ),
            recovery=assess_recovery(
                [
                    day
                    for day in all_days
                    if day.day < day.observed_at.astimezone(ZoneInfo(day.timezone)).date()
                ],
                end,
            ),
            last_observed_at=max((d.observed_at for d in days), default=None),
            limitations=[
                "Samsung-origin Health Connect aggregates only.",
                "Missing values are unknown, not zero.",
                "Sleep session duration and staged time are kept separate.",
                "Wearable heart rate, oxygen, VO2 max and energy are estimates, not diagnoses.",
                "Wearable energy is informational and never changes nutrition targets "
                "automatically.",
                "Phone synchronization can be delayed; inspect observed_at.",
                "Averages exclude the observation day because its totals are partial.",
            ],
        )

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from uuid import UUID
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from gym_coach.integrations.health_connect.service import HealthBatch
from gym_coach.tracking.activity import ActivityDay
from gym_coach.tracking.body import BodyMeasurementObservation

DATABASE_NAME = "health_connect_export.db"
SAMSUNG_HEALTH_PACKAGE = "com.sec.android.app.shealth"
OPENSCALE_SYNC_PACKAGES = ("com.health.openscale.sync", "com.health.openscale.sync.oss")
SUPPORTED_USER_VERSIONS = frozenset({26})
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_DATABASE_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 50
MILLISECONDS_PER_MINUTE = Decimal(60_000)
CALORIES_PER_KILOCALORIE = Decimal(1000)
SECONDS_PER_DAY = Decimal(86_400)
JOULES_PER_KILOCALORIE = Decimal(4184)
EPOCH = date(1970, 1, 1)

EXERCISE_TYPES = {
    4: "biking",
    8: "calisthenics",
    33: "running",
    49: "swimming_pool",
    53: "walking",
    55: "weightlifting",
    58: "other_workout",
}


class HealthConnectExportError(ValueError):
    """The Health Connect backup is unsafe, unsupported, or malformed."""


def parse_health_connect_export(
    archive: Path,
    *,
    request_id: UUID,
    observed_at: datetime,
    timezone: str,
    window_days: int = 30,
) -> HealthBatch:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise HealthConnectExportError("Export observation time must include a timezone")
    if not 1 <= window_days <= 90:
        raise HealthConnectExportError("Export window must contain 1 to 90 days")
    try:
        if archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise HealthConnectExportError("Health Connect archive exceeds the size limit")
        with ZipFile(archive) as bundle:
            infos = bundle.infolist()
            if len(infos) != 1 or infos[0].filename != DATABASE_NAME:
                raise HealthConnectExportError("Health Connect archive layout is unsupported")
            info = infos[0]
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or info.file_size > MAX_DATABASE_BYTES:
                raise HealthConnectExportError("Health Connect archive entry is unsafe")
            if (
                info.compress_size == 0
                or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise HealthConnectExportError("Health Connect archive compression is unsafe")
            if bundle.testzip() is not None:
                raise HealthConnectExportError("Health Connect archive checksum failed")
            with TemporaryDirectory(prefix="gym-coach-health-") as directory:
                database = Path(directory) / DATABASE_NAME
                with bundle.open(info) as source, database.open("wb") as destination:
                    while chunk := source.read(1024 * 1024):
                        destination.write(chunk)
                days, body_measurements = _read_database(
                    database,
                    observed_at=observed_at,
                    timezone=timezone,
                    window_days=window_days,
                )
    except (BadZipFile, OSError, sqlite3.Error) as exc:
        raise HealthConnectExportError("Health Connect export could not be read") from exc
    if not days and not body_measurements:
        raise HealthConnectExportError("No recent supported health records were found")
    return HealthBatch(
        request_id=request_id,
        consent_confirmed=True,
        days=days,
        body_measurements=body_measurements,
    )


def _read_database(
    database: Path,
    *,
    observed_at: datetime,
    timezone: str,
    window_days: int,
) -> tuple[list[ActivityDay], list[BodyMeasurementObservation]]:
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro&immutable=1", uri=True)
    try:
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise HealthConnectExportError("Health Connect database integrity check failed")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version not in SUPPORTED_USER_VERSIONS:
            raise HealthConnectExportError(
                f"Unsupported Health Connect export schema version: {version}"
            )
        _validate_schema(connection)
        samsung_ids = tuple(
            int(row[0])
            for row in connection.execute(
                "SELECT row_id FROM application_info_table WHERE package_name = ?",
                (SAMSUNG_HEALTH_PACKAGE,),
            )
        )
        openscale_ids = tuple(
            int(row[0])
            for row in connection.execute(
                "SELECT row_id FROM application_info_table WHERE package_name IN (?, ?)",
                OPENSCALE_SYNC_PACKAGES,
            )
        )
        try:
            last_day = observed_at.astimezone(ZoneInfo(timezone)).date()
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HealthConnectExportError("Health export timezone is unknown") from exc
        first_epoch_day = (last_day - timedelta(days=window_days - 1) - EPOCH).days
        last_epoch_day = (last_day - EPOCH).days
        daily: dict[date, dict[str, Any]] = {}
        if samsung_ids:
            grouped = [
                _group_steps(connection, samsung_ids, first_epoch_day, last_epoch_day),
                _group_sleep(connection, samsung_ids, first_epoch_day, last_epoch_day),
                _group_exercise(connection, samsung_ids, first_epoch_day, last_epoch_day),
                _group_heart_rate(connection, samsung_ids, first_epoch_day, last_epoch_day),
                _group_scalar(
                    connection,
                    "distance_record_table",
                    "distance",
                    samsung_ids,
                    first_epoch_day,
                    last_epoch_day,
                    "distance_meters",
                    "sum",
                ),
                _group_scalar(
                    connection,
                    "total_calories_burned_record_table",
                    "energy",
                    samsung_ids,
                    first_epoch_day,
                    last_epoch_day,
                    "total_energy_kcal",
                    "sum",
                    divisor=CALORIES_PER_KILOCALORIE,
                ),
                _group_scalar(
                    connection,
                    "resting_heart_rate_record_table",
                    "beats_per_minute",
                    samsung_ids,
                    first_epoch_day,
                    last_epoch_day,
                    "resting_heart_rate_bpm",
                    "avg",
                ),
                _group_scalar(
                    connection,
                    "heart_rate_variability_rmssd_record_table",
                    "heart_rate_variability_millis",
                    samsung_ids,
                    first_epoch_day,
                    last_epoch_day,
                    "hrv_rmssd_ms",
                    "avg",
                ),
                _group_oxygen(connection, samsung_ids, first_epoch_day, last_epoch_day),
                _group_scalar(
                    connection,
                    "vo2_max_record_table",
                    "vo2_milliliters_per_minute_kilogram",
                    samsung_ids,
                    first_epoch_day,
                    last_epoch_day,
                    "vo2_max_ml_min_kg",
                    "avg",
                ),
            ]
            for values in grouped:
                for day, fields in values.items():
                    daily.setdefault(day, {}).update(fields)
        days = [
            ActivityDay.model_validate(
                {
                    "day": day,
                    "timezone": timezone,
                    "observed_at": observed_at,
                    **daily[day],
                }
            )
            for day in sorted(daily)
        ]
        body_measurements = (
            _read_body_measurements(
                connection,
                openscale_ids,
                first_epoch_day,
                last_epoch_day,
                observed_at,
                timezone,
            )
            if openscale_ids
            else []
        )
        return days, body_measurements
    finally:
        connection.close()


def _validate_schema(connection: sqlite3.Connection) -> None:
    required = {
        "application_info_table": {"row_id", "package_name"},
        "steps_record_table": {"app_info_id", "local_date", "count"},
        "sleep_session_record_table": {
            "row_id",
            "app_info_id",
            "local_date",
            "start_time",
            "end_time",
        },
        "sleep_stages_table": {"parent_key", "stage_start_time", "stage_end_time", "stage_type"},
        "exercise_session_record_table": {
            "app_info_id",
            "local_date",
            "start_time",
            "end_time",
            "exercise_type",
        },
        "distance_record_table": {"app_info_id", "local_date", "distance"},
        "total_calories_burned_record_table": {"app_info_id", "local_date", "energy"},
        "heart_rate_record_table": {"row_id", "app_info_id", "local_date"},
        "heart_rate_record_series_table": {"parent_key", "beats_per_minute"},
        "resting_heart_rate_record_table": {"app_info_id", "local_date", "beats_per_minute"},
        "heart_rate_variability_rmssd_record_table": {
            "app_info_id",
            "local_date",
            "heart_rate_variability_millis",
        },
        "oxygen_saturation_record_table": {"app_info_id", "local_date", "percentage"},
        "vo2_max_record_table": {
            "app_info_id",
            "local_date",
            "vo2_milliliters_per_minute_kilogram",
        },
        "weight_record_table": {"uuid", "app_info_id", "local_date", "time", "weight"},
        "body_fat_record_table": {"row_id", "app_info_id", "time", "percentage"},
        "lean_body_mass_record_table": {"row_id", "app_info_id", "time", "mass"},
        "body_water_mass_record_table": {"row_id", "app_info_id", "time", "body_water_mass"},
        "bone_mass_record_table": {"row_id", "app_info_id", "time", "mass"},
        "basal_metabolic_rate_record_table": {
            "row_id",
            "app_info_id",
            "time",
            "basal_metabolic_rate",
        },
    }
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for table, expected_columns in required.items():
        if table not in tables:
            raise HealthConnectExportError(f"Required Health Connect table is missing: {table}")
        columns = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if not expected_columns <= columns:
            raise HealthConnectExportError(f"Health Connect table schema is unsupported: {table}")


def _placeholders(values: Iterable[int]) -> str:
    return ",".join("?" for _ in values)


def _group_steps(
    connection: sqlite3.Connection,
    app_ids: tuple[int, ...],
    first_day: int,
    last_day: int,
) -> dict[date, dict[str, Any]]:
    query = f"""
        SELECT local_date, SUM(count)
        FROM steps_record_table
        WHERE app_info_id IN ({_placeholders(app_ids)}) AND local_date BETWEEN ? AND ?
        GROUP BY local_date
    """
    rows = connection.execute(query, (*app_ids, first_day, last_day))
    return {EPOCH + timedelta(days=int(day)): {"steps": int(count)} for day, count in rows}


def _group_sleep(
    connection: sqlite3.Connection,
    app_ids: tuple[int, ...],
    first_day: int,
    last_day: int,
) -> dict[date, dict[str, Any]]:
    query = f"""
        SELECT row_id, local_date, start_time, end_time
        FROM sleep_session_record_table
        WHERE app_info_id IN ({_placeholders(app_ids)}) AND local_date BETWEEN ? AND ?
    """
    rows = connection.execute(query, (*app_ids, first_day, last_day))
    result: dict[date, dict[str, Any]] = {}
    longest: dict[date, int] = {}
    for _, epoch_day, start, end in rows:
        day = EPOCH + timedelta(days=int(epoch_day))
        duration = max(0, int(end) - int(start))
        fields = result.setdefault(
            day, {"sleep_session_minutes": Decimal(0), "sleep_session_count": 0}
        )
        fields["sleep_session_minutes"] = Decimal(fields["sleep_session_minutes"]) + (
            Decimal(duration) / MILLISECONDS_PER_MINUTE
        )
        fields["sleep_session_count"] = int(fields["sleep_session_count"]) + 1
        if duration > longest.get(day, -1):
            longest[day] = duration
            fields["main_sleep_start_at"] = datetime.fromtimestamp(
                int(start) / 1000, tz=ZoneInfo("UTC")
            )
            fields["main_sleep_end_at"] = datetime.fromtimestamp(
                int(end) / 1000, tz=ZoneInfo("UTC")
            )
    stage_query = f"""
        SELECT session.local_date, stage.stage_type,
               SUM(MAX(0, stage.stage_end_time - stage.stage_start_time))
        FROM sleep_stages_table AS stage
        JOIN sleep_session_record_table AS session ON session.row_id = stage.parent_key
        WHERE session.app_info_id IN ({_placeholders(app_ids)})
          AND session.local_date BETWEEN ? AND ?
        GROUP BY session.local_date, stage.stage_type
    """
    for epoch_day, stage_type, duration in connection.execute(
        stage_query, (*app_ids, first_day, last_day)
    ):
        day = EPOCH + timedelta(days=int(epoch_day))
        fields = result.setdefault(day, {})
        minutes = Decimal(int(duration)) / MILLISECONDS_PER_MINUTE
        field = {
            0: None,
            1: "sleep_awake_minutes",
            2: "sleep_asleep_minutes",
            3: "sleep_awake_minutes",
            4: "sleep_light_minutes",
            5: "sleep_deep_minutes",
            6: "sleep_rem_minutes",
            7: "sleep_awake_minutes",
        }.get(int(stage_type))
        if field is not None:
            fields[field] = Decimal(fields.get(field, 0)) + minutes
        if int(stage_type) in {2, 4, 5, 6}:
            fields["sleep_asleep_minutes"] = (
                Decimal(fields.get("sleep_asleep_minutes", 0)) + minutes
                if int(stage_type) != 2
                else Decimal(fields.get("sleep_asleep_minutes", 0))
            )
    return result


def _group_exercise(
    connection: sqlite3.Connection,
    app_ids: tuple[int, ...],
    first_day: int,
    last_day: int,
) -> dict[date, dict[str, Any]]:
    query = f"""
        SELECT local_date, exercise_type, COUNT(*), SUM(MAX(0, end_time - start_time))
        FROM exercise_session_record_table
        WHERE app_info_id IN ({_placeholders(app_ids)}) AND local_date BETWEEN ? AND ?
        GROUP BY local_date, exercise_type
    """
    result: dict[date, dict[str, Any]] = {}
    for epoch_day, exercise_type, count, duration in connection.execute(
        query, (*app_ids, first_day, last_day)
    ):
        day = EPOCH + timedelta(days=int(epoch_day))
        fields = result.setdefault(
            day,
            {
                "exercise_session_count": 0,
                "exercise_minutes": Decimal(0),
                "exercise_minutes_by_type": {},
            },
        )
        minutes = Decimal(int(duration)) / MILLISECONDS_PER_MINUTE
        fields["exercise_session_count"] = int(fields["exercise_session_count"]) + int(count)
        fields["exercise_minutes"] = Decimal(fields["exercise_minutes"]) + minutes
        by_type = fields["exercise_minutes_by_type"]
        assert isinstance(by_type, dict)
        key = EXERCISE_TYPES.get(int(exercise_type), f"health_connect_type_{exercise_type}")
        by_type[key] = minutes
    return result


def _group_heart_rate(
    connection: sqlite3.Connection,
    app_ids: tuple[int, ...],
    first_day: int,
    last_day: int,
) -> dict[date, dict[str, Any]]:
    query = f"""
        SELECT record.local_date, COUNT(*), AVG(sample.beats_per_minute),
               MIN(sample.beats_per_minute), MAX(sample.beats_per_minute)
        FROM heart_rate_record_series_table AS sample
        JOIN heart_rate_record_table AS record ON record.row_id = sample.parent_key
        WHERE record.app_info_id IN ({_placeholders(app_ids)})
          AND record.local_date BETWEEN ? AND ?
        GROUP BY record.local_date
    """
    return {
        EPOCH + timedelta(days=int(day)): {
            "heart_rate_sample_count": int(count),
            "mean_heart_rate_bpm": Decimal(str(mean)),
            "min_heart_rate_bpm": int(minimum),
            "max_heart_rate_bpm": int(maximum),
        }
        for day, count, mean, minimum, maximum in connection.execute(
            query, (*app_ids, first_day, last_day)
        )
    }


def _group_scalar(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    app_ids: tuple[int, ...],
    first_day: int,
    last_day: int,
    field: str,
    aggregate: str,
    *,
    divisor: Decimal = Decimal(1),
) -> dict[date, dict[str, Any]]:
    if aggregate not in {"sum", "avg"}:
        raise AssertionError("Unsupported aggregate")
    query = f"""
        SELECT local_date, {aggregate.upper()}({column})
        FROM {table}
        WHERE app_info_id IN ({_placeholders(app_ids)}) AND local_date BETWEEN ? AND ?
        GROUP BY local_date
    """
    return {
        EPOCH + timedelta(days=int(day)): {field: Decimal(str(value)) / divisor}
        for day, value in connection.execute(query, (*app_ids, first_day, last_day))
        if value is not None
    }


def _group_oxygen(
    connection: sqlite3.Connection,
    app_ids: tuple[int, ...],
    first_day: int,
    last_day: int,
) -> dict[date, dict[str, Any]]:
    query = f"""
        SELECT local_date, COUNT(*), AVG(percentage), MIN(percentage)
        FROM oxygen_saturation_record_table
        WHERE app_info_id IN ({_placeholders(app_ids)}) AND local_date BETWEEN ? AND ?
        GROUP BY local_date
    """
    return {
        EPOCH + timedelta(days=int(day)): {
            "oxygen_saturation_sample_count": int(count),
            "mean_oxygen_saturation_percent": Decimal(str(mean)),
            "min_oxygen_saturation_percent": Decimal(str(minimum)),
        }
        for day, count, mean, minimum in connection.execute(query, (*app_ids, first_day, last_day))
    }


def _read_body_measurements(
    connection: sqlite3.Connection,
    app_ids: tuple[int, ...],
    first_day: int,
    last_day: int,
    observed_at: datetime,
    timezone: str,
) -> list[BodyMeasurementObservation]:
    query = f"""
        SELECT
            weight.uuid,
            weight.local_date,
            weight.time,
            weight.weight,
            (
                SELECT fat.percentage
                FROM body_fat_record_table AS fat
                WHERE fat.app_info_id = weight.app_info_id AND fat.time = weight.time
                ORDER BY fat.row_id
                LIMIT 1
            ),
            (SELECT lean.mass FROM lean_body_mass_record_table AS lean
             WHERE lean.app_info_id = weight.app_info_id AND lean.time = weight.time
             ORDER BY lean.row_id LIMIT 1),
            (SELECT water.body_water_mass FROM body_water_mass_record_table AS water
             WHERE water.app_info_id = weight.app_info_id AND water.time = weight.time
             ORDER BY water.row_id LIMIT 1),
            (SELECT bone.mass FROM bone_mass_record_table AS bone
             WHERE bone.app_info_id = weight.app_info_id AND bone.time = weight.time
             ORDER BY bone.row_id LIMIT 1),
            (SELECT bmr.basal_metabolic_rate FROM basal_metabolic_rate_record_table AS bmr
             WHERE bmr.app_info_id = weight.app_info_id AND bmr.time = weight.time
             ORDER BY bmr.row_id LIMIT 1)
        FROM weight_record_table AS weight
        WHERE weight.app_info_id IN ({_placeholders(app_ids)})
          AND weight.local_date BETWEEN ? AND ?
        ORDER BY weight.time, weight.row_id
    """
    rows = connection.execute(query, (*app_ids, first_day, last_day))
    result = []
    for (
        external_id,
        local_day,
        measured_at,
        weight_grams,
        body_fat,
        lean_grams,
        water_grams,
        bone_grams,
        bmr_watts,
    ) in rows:
        if not isinstance(external_id, bytes) or len(external_id) != 16:
            raise HealthConnectExportError("Health Connect body measurement ID is malformed")
        result.append(
            BodyMeasurementObservation(
                external_id=UUID(bytes=external_id),
                measured_at=datetime.fromtimestamp(int(measured_at) / 1000, tz=ZoneInfo("UTC")),
                measured_on=EPOCH + timedelta(days=int(local_day)),
                timezone=timezone,
                weight_kg=Decimal(str(weight_grams)) / Decimal(1000),
                body_fat_percent=Decimal(str(body_fat)) if body_fat is not None else None,
                body_fat_method="consumer_bia" if body_fat is not None else None,
                lean_body_mass_kg=(
                    Decimal(str(lean_grams)) / Decimal(1000) if lean_grams is not None else None
                ),
                body_water_mass_kg=(
                    Decimal(str(water_grams)) / Decimal(1000) if water_grams is not None else None
                ),
                bone_mass_kg=(
                    Decimal(str(bone_grams)) / Decimal(1000) if bone_grams is not None else None
                ),
                basal_metabolic_rate_kcal=(
                    Decimal(str(bmr_watts)) * SECONDS_PER_DAY / JOULES_PER_KILOCALORIE
                    if bmr_watts is not None
                    else None
                ),
                observed_at=observed_at,
            )
        )
    return result
